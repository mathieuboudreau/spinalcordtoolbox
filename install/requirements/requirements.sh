#!/bin/bash
# 
#Installer for requirements
#
echo "--------------------------"
echo "INSTALLER FOR REQUIREMENTS"
echo "--------------------------"
# Installation using Conda
if which conda >/dev/null; then
    echo "* CONDA *"
    conda install --yes --file requirementsConda.txt
else
    echo "ERROR: Conda is not installed. Cannot install dependences."
fi
# Installation using Pip
if which pip >/dev/null; then
    echo "* PIP *"
    pip install -r requirementsPip.txt
else
    echo "ERROR: Pip is not installed. Cannot install dependences."
fi
# Installation using easy_install
if which easy_install >/dev/null; then
    echo "* EASY_INSTALL *"
    easy_install dipy install -r requirementsPip.txt
else
    echo "ERROR: easy_install is not installed. Cannot install dependences."
fi
