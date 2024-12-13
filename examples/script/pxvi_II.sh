#!/bin/bash

# Resource management for local execution
# Adjust these values based on your machine's capabilities
export OMP_NUM_THREADS=32  # Adjust to your CPU core count
export MALLOC_ARENA_MAX=4  # Helps prevent memory fragmentation

### Pixel to hexagon
# Minimal required input: path, iden, input, width
# Alternative: env, path, input, output, width

# Default parameters
key=Count
major_axis=Y
sliding_step=2
mu_scale=1
min_ct_per_unit=50
overwrite=0

# Parse command line arguments
for ARGUMENT in "$@"
do
   KEY=$(echo $ARGUMENT | cut -f1 -d=)
   KEY_LENGTH=${#KEY}
   VALUE="${ARGUMENT:$KEY_LENGTH+1}"
   export "$KEY"="$VALUE"
done

# Error handling
set -xe
set -o pipefail

# Source environment if provided
if [ ! -z "${env}" ]; then
    source ${env}
fi

# Process output filename
out=$(echo $output | sed 's/\.gz$//g')

# Run ficture with specified parameters
ficture make_dge \
    --key ${key} \
    --count_header ${key} \
    --input ${input} \
    --output ${out} \
    --hex_width ${width} \
    --n_move ${sliding_step} \
    --min_ct_per_unit ${min_ct_per_unit} \
    --mu_scale ${mu_scale} \
    --precision 2 \
    --major_axis ${major_axis}

# Sort and compress output
sort -S 75% -k1,1n ${out} | gzip -c > ${output}  # Using 75% of available RAM for sorting
rm ${out}

./local_processing.sh input=/path/to/input width=10 output=/path/to/output.gz env=/home/eecs/martinalvarezkuglen/.cache/pypoetry/virtualenvs/pixelvi-eO-HYK6l-py3.11

ficture run_together \
    --in-tsv examples/data/transcripts.tsv.gz \
    --in-minmax examples/data/coordinate_minmax.tsv \
    --in-feature examples/data/feature.clean.tsv.gz \
    --out-dir output1 --all

# Add data dir variable
DATA_DIR="/data/yosef2/martinak/Xenium IPF 225721/"
ficture run_together \
    --in-tsv "${DATA_DIR}/filtered.matrix.tsv.gz" \
    --in-minmax "${DATA_DIR}/coordinate_minmax.tsv" \
    --in-feature "${DATA_DIR}/features.tsv.gz" \
    --out-dir "${DATA_DIR}/ficture_output" \
    --train-width 12 \
    --n-factor 12,18 \
    --n-jobs 24 \
    --plot-each-factor \
    --all


# Make pixel level figures
n_factor=12
pixel_resolution=0.5
output_id="nF${n_factor}.d_12"
output_path="${DATA_DIR}/ficture_output/analysis/${output_id}/"
figure_path="${output_path}/figure/"
prefix="${output_id}.decode.prj_12.r_4_5"
cmap="${output_path}/figure/${output_id}.rgb.tsv"
input="${output_path}/${prefix}.pixel.sorted.tsv.gz"
output="${figure_path}/${prefix}.pixel.png"
ficture plot_pixel_full --input ${input} --color_table ${cmap} --output ${output} --plot_um_per_pixel ${pixel_resolution} --full
