#!/bin/bash

# This script will run the Ficture package 

# Check if a path argument is provided
if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <path_to_data_directory>"
    exit 1
fi

# Set the path from the first argument
path="$1"

# Set input and output paths
input="${path}/transcripts.csv.gz"
output="${path}/filtered.matrix.tsv"
feature="${path}/features.tsv.gz"

# Run the Python script
python format_xenium.py --input "${input}" --output "${output}" --feature "${feature}" --min_phred_score 15 --dummy_genes BLANK\|NegCon

# Sort and compress the output
sort -k2,2g "${output}" | gzip -c > "${output}.gz"

# Remove the uncompressed output
rm "${output}"
