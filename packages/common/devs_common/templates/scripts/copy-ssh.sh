#!/bin/bash
# Copy SSH directory if it exists, otherwise create empty directory
if [ -d ".ssh" ]; then
    echo "SSH directory found, will be copied by Dockerfile"
else
    echo "No .ssh directory found, creating empty directory for Dockerfile"
    mkdir -p .ssh
    touch .ssh/.keep
fi