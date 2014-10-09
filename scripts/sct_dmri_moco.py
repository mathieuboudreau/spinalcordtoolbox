#!/usr/bin/env python
#########################################################################################
#
# Motion correction of dMRI data.
#
# Inspired by Xu et al. Neuroimage 2013.
#
# Details of the algorithm:
# - grouping of DW data only (every n volumes, default n=5)
# - average all b0
# - average DWI data within each group
# - average DWI of all groups
# - moco on DWI groups
# - moco on b=0, using target volume: last b=0
# - moco on all dMRI data
# _ generating b=0 mean and DWI mean after motion correction
#
# ---------------------------------------------------------------------------------------
# Copyright (c) 2013 Polytechnique Montreal <www.neuro.polymtl.ca>
# Authors: Karun Raju, Tanguy Duval, Julien Cohen-Adad
# Modified: 2014-08-15
#
# About the license: see the file LICENSE.TXT
#########################################################################################

# TODO: make sure slicewise not used with ants, eddy not used with ants
# TODO: make sure images are axial
# TDOD: if -f, we only need two plots. Plot 1: X params with fitted spline, plot 2: Y param with fitted splines. Each plot will have all Z slices (with legend Z=0, Z=1, ...) and labels: y; translation (mm), xlabel: volume #. Plus add grid.
# TODO (no priority): for sinc interp, use ANTs or sct_c3d instead of flirt

import sys
import os
import commands
import getopt
import time
import glob
import math
import numpy as np
from sct_dmri_eddy_correct import eddy_correct
import sct_utils as sct
import msct_moco as moco
from sct_dmri_separate_b0_and_dwi import identify_b0

class param:
    def __init__(self):
        self.debug = 0
        self.fname_data = ''
        self.fname_bvecs = ''
        self.fname_bvals = ''
        self.fname_target = ''
        self.fname_centerline = ''
        # self.path_out = ''
        self.mat_final = ''
        self.todo = ''
        self.dwi_group_size = 3  # number of images averaged for 'dwi' method.
        self.spline_fitting = 0
        self.remove_tmp_files = 1
        self.verbose = 1
        self.plot_graph = 0
        # param for msct_moco
        self.slicewise = 0
        self.suffix = '_moco'
        self.mask_size = 0  # sigma of gaussian mask in mm --> std of the kernel. Default is 0
        self.program = 'slicereg'  # flirt, ants, ants_affine, slicereg
        self.file_schedule = '/flirtsch/schedule_TxTy.sch'  # /flirtsch/schedule_TxTy_2mm.sch, /flirtsch/schedule_TxTy.sch
        # self.cost_function_flirt = ''  # 'mutualinfo' | 'woods' | 'corratio' | 'normcorr' | 'normmi' | 'leastsquares'. Default is 'normcorr'.
        self.interp = 'spline'  # nn, linear, spline
        #Eddy Current Distortion Parameters:
        self.run_eddy = 0
        self.mat_eddy = ''
        self.min_norm = 0.001
        self.swapXY = 0
        self.bval_min = 100  # in case user does not have min bvalues at 0, set threshold (where csf disapeared).


#=======================================================================================================================
# main
#=======================================================================================================================
def main():

    print '\n\n\n\n==================================================='
    print '          Running: sct_dmri_moco'
    print '===================================================\n\n\n\n'

    # initialization
    start_time = time.time()
    path_out = '.'

    # get path of the toolbox
    status, path_sct = commands.getstatusoutput('echo $SCT_DIR')

    # Parameters for debug mode
    if param.debug:
        # get path of the testing data
        status, path_sct_data = commands.getstatusoutput('echo $SCT_TESTING_DATA_DIR')
        param.fname_data = path_sct_data+'/dmri/dmri.nii.gz'
        param.fname_bvecs = path_sct_data+'/dmri/bvecs.txt'
        param.fname_bvals = ''  # path_sct_data+'/errsm_03_sub/dmri/bvecs.txt'
        param.verbose = 1
        param.slicewise = 0
        param.run_eddy = 0
        param.program = 'slicereg'  # ants_affine, flirt

    # Check input parameters
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hi:a:b:c:d:e:f:g:l:m:o:p:r:s:v:z:')
    except getopt.GetoptError:
        usage()
    for opt, arg in opts:
        if opt == '-h':
            usage()
        elif opt in ('-a'):
            param.fname_bvals = arg
        elif opt in ('-b'):
            param.fname_bvecs = arg
        elif opt in ('-c'):
            param.cost_function_flirt = arg
        elif opt in ('-d'):
            param.dwi_group_size = int(arg)
        elif opt in ('-e'):
            param.run_eddy = int(arg)
        elif opt in ('-f'):
            param.spline_fitting = int(arg)
        elif opt in ('-g'):
            param.plot_graph = int(arg)
        elif opt in ('-i'):
            param.fname_data = arg
        elif opt in ('-l'):
            param.fname_centerline = arg
        elif opt in ('-m'):
            param.program = arg
        elif opt in ('-o'):
            path_out = arg
        elif opt in ('-p'):
            param.interp = arg
        elif opt in ('-r'):
            param.remove_tmp_files = int(arg)
        elif opt in ('-s'):
            param.mask_size = float(arg)
        elif opt in ('-v'):
            param.verbose = int(arg)
        elif opt in ('-z'):
            param.slicewise = int(arg)

    # display usage if a mandatory argument is not provided
    if param.fname_data == '' or param.fname_bvecs == '':
        sct.printv('ERROR: All mandatory arguments are not provided. See usage.', 1, 'error')
        usage()

    # if param.cost_function_flirt == '':
    #     param.cost_function_flirt = 'normcorr'

    # if param.path_out == '':
    #     path_out = ''
    #     param.path_out = os.getcwd() + '/'
    # global path_out
    # path_out = param.path_out

    sct.printv('\nInput parameters:', param.verbose)
    sct.printv('  input file ............'+param.fname_data, param.verbose)
    sct.printv('  bvecs file ............'+param.fname_bvecs, param.verbose)
    sct.printv('  bvals file ............'+param.fname_bvals, param.verbose)

    # check existence of input files
    sct.printv('\nCheck file existence...', param.verbose)
    sct.check_file_exist(param.fname_data, param.verbose)
    sct.check_file_exist(param.fname_bvecs, param.verbose)
    if not param.fname_bvals == '':
        sct.check_file_exist(param.fname_bvals, param.verbose)

    # Get full path
    param.fname_data = os.path.abspath(param.fname_data)
    param.fname_bvecs = os.path.abspath(param.fname_bvecs)
    if param.fname_bvals != '':
        param.fname_bvals = os.path.abspath(param.fname_bvals)

    # Extract path, file and extension
    path_data, file_data, ext_data = sct.extract_fname(param.fname_data)

    # create temporary folder
    sct.printv('\nCreate temporary folder...', param.verbose)
    path_tmp = sct.slash_at_the_end('tmp.'+time.strftime("%y%m%d%H%M%S"), 1)
    sct.run('mkdir '+path_tmp, param.verbose)

    # Copying input data to tmp folder and convert to nii
    # NB: cannot use c3d here because c3d cannot convert 4D data.
    sct.printv('\nCopying input data to tmp folder and convert to nii...', param.verbose)
    sct.run('cp '+param.fname_data+' '+path_tmp+'dmri'+ext_data, param.verbose)
    sct.run('cp '+param.fname_bvecs+' '+path_tmp+'bvecs.txt', param.verbose)

    # go to tmp folder
    os.chdir(path_tmp)

    # convert dmri to nii format
    sct.run('fslchfiletype NIFTI dmri', param.verbose)

    # EDDY CURRENT CORRECTION
    # TODO: MAKE SURE path_out IS CORRECT WITH EDDY BEFORE ACTIVATING EDDY
    # if param.run_eddy:
    #     param.path_out = ''
    #     param.slicewise = 1
    #     eddy_correct(param)
    #     param.fname_data = file_data + '_eddy.nii'

    # run moco
    dmri_moco(param)

    # come back to parent folder
    os.chdir('..')

    # Generate output files
    path_out = sct.slash_at_the_end(path_out, 1)
    sct.create_folder(path_out)
    sct.printv('\nGenerate output files...', param.verbose)
    sct.generate_output_file(path_tmp+'dmri'+param.suffix+'.nii', path_out+file_data+param.suffix+ext_data, param.verbose)
    sct.generate_output_file(path_tmp+'b0_mean.nii', path_out+'b0'+param.suffix+'_mean'+ext_data, param.verbose)
    sct.generate_output_file(path_tmp+'dwi_mean.nii', path_out+'dwi'+param.suffix+'_mean'+ext_data, param.verbose)

    # Delete temporary files
    if param.remove_tmp_files == 1:
        sct.printv('\nDelete temporary files...', param.verbose)
        sct.run('rm -rf '+path_tmp, param.verbose)

    # display elapsed time
    elapsed_time = time.time() - start_time
    print '\nFinished! Elapsed time: '+str(int(round(elapsed_time)))+'s'

    #To view results
    print '\nTo view results, type:'
    print 'fslview -m ortho,ortho '+param.path_out+file_data+param.suffix+' '+file_data+' &\n'


#=======================================================================================================================
# dmri_moco: motion correction specific to dmri data
#=======================================================================================================================
def dmri_moco(param):

    file_data = 'dmri'
    file_b0 = 'b0'
    file_dwi = 'dwi'
    mat_final = 'mat_final/'
    fsloutput = 'export FSLOUTPUTTYPE=NIFTI; '  # for faster processing, all outputs are in NIFTI
    
    # fname_data = param.fname_data
    # fname_bvecs = param.fname_bvecs
    # fname_bvals = param.fname_bvals
    # slicewise = param.slicewise
    # dwi_group_size = param.dwi_group_size
    # interp = param.interp
    # verbose = param.verbose
    # bval_min = param.bval_min
    #
    # # Extract path, file and extension
    # path_data, file_data, ext_data = sct.extract_fname(fname_data)
    #
    # file_b0 = 'b0'
    # file_dwi = 'dwi'
    
    # Get dimensions of data
    sct.printv('\nGet dimensions of data...', param.verbose)
    nx, ny, nz, nt, px, py, pz, pt = sct.get_dimension(file_data+'.nii')
    sct.printv('  ' + str(nx) + ' x ' + str(ny) + ' x ' + str(nz), param.verbose)

    # Identify b=0 and DWI images
    sct.printv('\nIdentify b=0 and DWI images...', param.verbose)
    index_b0, index_dwi, nb_b0, nb_dwi = identify_b0('bvecs.txt', param.fname_bvals, param.bval_min, param.verbose)

    #=======================================================================================================================
    # Prepare NIFTI (mean/groups...)
    #=======================================================================================================================
    # Split into T dimension
    sct.printv('\nSplit along T dimension...', param.verbose)
    status, output = sct.run(fsloutput+'fslsplit ' + file_data + ' ' + file_data + '_T', param.verbose)

    # Merge b=0 images
    sct.printv('\nMerge b=0...', param.verbose)
    cmd = fsloutput + 'fslmerge -t ' + file_b0
    for it in range(nb_b0):
        cmd = cmd + ' ' + file_data + '_T' + str(index_b0[it]).zfill(4)
    status, output = sct.run(cmd, param.verbose)
    sct.printv(('  File created: ' + file_b0), param.verbose)

    # Average b=0 images
    sct.printv('\nAverage b=0...', param.verbose)
    file_b0_mean = file_b0+'_mean'
    cmd = fsloutput + 'fslmaths ' + file_b0 + ' -Tmean ' + file_b0_mean
    status, output = sct.run(cmd, param.verbose)

    # Number of DWI groups
    nb_groups = int(math.floor(nb_dwi/param.dwi_group_size))
    
    # Generate groups indexes
    group_indexes = []
    for iGroup in range(nb_groups):
        group_indexes.append(index_dwi[(iGroup*param.dwi_group_size):((iGroup+1)*param.dwi_group_size)])
    
    # add the remaining images to the last DWI group
    nb_remaining = nb_dwi%param.dwi_group_size  # number of remaining images
    if nb_remaining > 0:
        nb_groups += 1
        group_indexes.append(index_dwi[len(index_dwi)-nb_remaining:len(index_dwi)])

    # DWI groups
    for iGroup in range(nb_groups):
        sct.printv('\nDWI group: ' +str((iGroup+1))+'/'+str(nb_groups), param.verbose)

        # get index
        index_dwi_i = group_indexes[iGroup]
        nb_dwi_i = len(index_dwi_i)

        # Merge DW Images
        sct.printv('Merge DW images...', param.verbose)
        file_dwi_merge_i = file_dwi + '_' + str(iGroup)
        cmd = fsloutput + 'fslmerge -t ' + file_dwi_merge_i
        for it in range(nb_dwi_i):
            cmd = cmd +' ' + file_data + '_T' + str(index_dwi_i[it]).zfill(4)
        sct.run(cmd, param.verbose)

        # Average DW Images
        sct.printv('Average DW images...', param.verbose)
        file_dwi_mean = file_dwi + '_mean_' + str(iGroup)
        cmd = fsloutput + 'fslmaths ' + file_dwi_merge_i + ' -Tmean ' + file_dwi_mean
        sct.run(cmd, param.verbose)

    # Merge DWI groups means
    sct.printv('\nMerging DW files...', param.verbose)
    file_dwi_groups_means_merge = 'dwi_averaged_groups'
    cmd = fsloutput + 'fslmerge -t ' + file_dwi_groups_means_merge
    for iGroup in range(nb_groups):
        cmd = cmd + ' ' + file_dwi + '_mean_' + str(iGroup)
    sct.run(cmd, param.verbose)

    # Average DW Images
    sct.printv('\nAveraging all DW images...', param.verbose)
    fname_dwi_mean = 'dwi_mean'  
    sct.run(fsloutput + 'fslmaths ' + file_dwi_groups_means_merge + ' -Tmean ' + file_dwi_mean, param.verbose)

    #=======================================================================================================================
    #START MOCO
    #=======================================================================================================================

    # Estimate moco on b0 groups
    sct.printv('\n-------------------------------------------------------------------------------', param.verbose)
    sct.printv('  Estimating motion on b=0 images...', param.verbose)
    sct.printv('-------------------------------------------------------------------------------', param.verbose)
    param_moco = param
    param_moco.file_data = 'b0'
    if index_dwi[0] != 0:
        # If first DWI is not the first volume (most common), then there is a least one b=0 image before. In that case
        # select it as the target image for registration of all b=0
        param_moco.file_target = file_data + '_T' + str(index_b0[index_dwi[0]-1]).zfill(4)
    else:
        # If first DWI is the first volume, then the target b=0 is the first b=0 from the index_b0.
        param_moco.file_target = file_data + '_T' + str(index_b0[0]).zfill(4)
    param_moco.path_out = ''
    param_moco.todo = 'estimate'
    param_moco.mat_moco = 'mat_b0groups'
    moco.moco(param_moco)

    # Estimate moco on dwi groups
    sct.printv('\n-------------------------------------------------------------------------------', param.verbose)
    sct.printv('  Estimating motion on DW images...', param.verbose)
    sct.printv('-------------------------------------------------------------------------------', param.verbose)
    param_moco.file_data = 'dwi_averaged_groups'
    param_moco.file_target = file_dwi + '_mean_' + str(0)  # target is the first DW image (closest to the first b=0)
    param_moco.path_out = ''
    #param_moco.todo = 'estimate'
    param_moco.todo = 'estimate_and_apply'
    param_moco.mat_moco = 'mat_dwigroups'
    moco.moco(param_moco)

    # create final mat folder
    sct.create_folder(mat_final)

    # Copy b=0 registration matrices
    sct.printv('\nCopy b=0 registration matrices...', param.verbose)
    # first, use the right extension
    # TODO: output param in moco so that we don't need to do the following twice
    if param.program == 'flirt':
        ext_mat = '.txt'  # affine matrix
    elif param.program == 'ants':
        ext_mat = '0Warp.nii.gz'  # warping field
    elif param.program == 'slicereg':
        ext_mat = 'Warp.nii.gz'  # warping field
    elif param.program == 'ants_affine' or param.program == 'ants_rigid':
        ext_mat = '0GenericAffine.mat'  # ITK affine matrix

    for it in range(nb_b0):
        if param.slicewise:
            for iz in range(nz):
                sct.run('cp '+'mat_b0groups/'+'mat.T'+str(it)+'_Z'+str(iz)+ext_mat+' '+mat_final+'mat.T'+str(index_b0[it])+'_Z'+str(iz)+ext_mat, param.verbose)
        else:
            sct.run('cp '+'mat_b0groups/'+'mat.T'+str(it)+ext_mat+' '+mat_final+'mat.T'+str(index_b0[it])+ext_mat, param.verbose)

    # Copy DWI registration matrices
    sct.printv('\nCopy DWI registration matrices...', param.verbose)
    for iGroup in range(nb_groups):
        for dwi in range(len(group_indexes[iGroup])):
            if param.slicewise:
                for iz in range(nz):
                    sct.run('cp '+'mat_dwigroups/'+'mat.T'+str(iGroup)+'_Z'+str(iz)+ext_mat+' '+mat_final+'mat.T'+str(group_indexes[iGroup][dwi])+'_Z'+str(iz)+ext_mat, param.verbose)
            else:
                sct.run('cp '+'mat_dwigroups/'+'mat.T'+str(iGroup)+ext_mat+' '+mat_final+'mat.T'+str(group_indexes[iGroup][dwi])+ext_mat, param.verbose)

    # Spline Regularization along T
    if param.spline_fitting:
        moco.spline(mat_final, nt, nz, param.verbose, np.array(index_b0), param.plot_graph)

    # combine Eddy Matrices
    if param.run_eddy:
        param.mat_2_combine = 'mat_eddy'
        param.mat_final = mat_final
        moco.combine_matrix(param)

    # Apply moco on all dmri data
    sct.printv('\n-------------------------------------------------------------------------------', param.verbose)
    sct.printv('  Apply moco', param.verbose)
    sct.printv('-------------------------------------------------------------------------------', param.verbose)
    param_moco.file_data = 'dmri'
    param_moco.file_target = file_dwi+'_mean_'+str(0)  # reference for reslicing into proper coordinate system
    param_moco.path_out = ''
    param_moco.mat_moco = mat_final
    param_moco.todo = 'apply'
    moco.moco(param_moco)

    # copy geometric information from header
    # NB: this is required because WarpImageMultiTransform in 2D mode wrongly sets pixdim(3) to "1".
    sct.run(fsloutput+'fslcpgeom dmri dmri_moco')

    # generate b0_moco_mean and dwi_moco_mean
    cmd = 'sct_dmri_separate_b0_and_dwi -i dmri'+param.suffix+'.nii -b bvecs.txt -a 1'
    if not param.fname_bvals == '':
        cmd = cmd+' -m '+param.fname_bvals
    sct.run(cmd, param.verbose)


#=======================================================================================================================
# usage
#=======================================================================================================================
def usage():
    print """
"""+os.path.basename(__file__)+"""
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Part of the Spinal Cord Toolbox <https://sourceforge.net/projects/spinalcordtoolbox>

DESCRIPTION
  Motion correction of DWI data. Uses slice-by-slice and group-wise registration. Outputs are:
  - motion-corrected data (with suffix _moco)
  - mean b=0 data (b0_mean)
  - mean dwi data (dwi_mean)

USAGE
  """+os.path.basename(__file__)+""" -i <dmri> -b <bvecs>

MANDATORY ARGUMENTS
  -i <dmri>        diffusion data
  -b <bvecs>       bvecs file

OPTIONAL ARGUMENTS
  -z {0,1}         slice-by-slice motion correction. Default="""+str(param.slicewise)+"""
  -d <nvols>       group nvols successive DWI volumes for more robustness. Default="""+str(param.dwi_group_size)+"""
  -e {0,1}         Eddy Correction using opposite gradient directions.  Default="""+str(param.run_eddy)+"""
                   N.B. Only use this option if pairs of opposite gradient images were adjacent
                   in time
  -s <int>         Size of Gaussian mask for more robust motion correction (in mm). 
                   For no mask, put 0. Default=0
                   N.B. if centerline is provided, mask is centered on centerline. If not, mask
                   is centered in the middle of each slice.
  -l <centerline>  (requires -s). Centerline file to specify the centre of Gaussian Mask.
  -f {0,1}         spline regularization along T. Default="""+str(param.spline_fitting)+"""
                   N.B. Use only if you want to correct large drifts with time.
  -m {method}      Method for registration:
                     slicereg: slicewise regularized Tx and Ty transformations (based on ANTs). Disregard "-z"
                     ants: non-rigid deformation constrained in axial plane. HIGHLY EXPERIMENTAL!
                     ants_affine: affine transformation constrained in axial plane.
                     ants_rigid: rigid transformation constrained in axial plane.
                     flirt: FSL flirt with Tx and Ty transformations.
                     Default="""+str(param.program)+"""
  -a <bvals>       bvals file. Used to identify low b-values (in case different from 0).
  -o <path_out>    Output path.
  -p {nn,linear,spline}  Final Interpolation. Default="""+str(param.interp)+"""
  -g {0,1}         display graph of moco parameters. Default="""+str(param.plot_graph)+"""
  -v {0,1}         verbose. Default="""+str(param.verbose)+"""
  -r {0,1}         remove temporary files. Default="""+str(param.remove_tmp_files)+"""
  -h               help. Show this message

EXAMPLE
  """+os.path.basename(__file__)+""" -i dmri.nii.gz -b bvecs.txt\n"""
    
    #Exit Program
    sys.exit(2)

#=======================================================================================================================
# Start program
#=======================================================================================================================
if __name__ == "__main__":
    param = param()
    main()