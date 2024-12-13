#!/bin/bash

#SBATCH --output=/home/%u/out/%x-%j.log
#SBATCH --time=80:00:00

#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --mem-per-cpu=7g

### Model fitting
# Minimal required input: path, nFactor
# Alternative - path, nFactor, hexagon, pixel, model_id, output_id

nFactor=12
path="/data/yosef2/martinak/XeniumIPF225721"

key=Count
major_axis=Y
mu_scale=1
min_ct_per_unit=50
min_ct_per_unit_fit=20
min_ct_per_feature=50

thread=24
R=10
train_nEpoch=1
train_width=12
fit_width=12
anchor_res=4

cmap_name="turbo"

# For DE output
max_pval_output=1e-3
min_fold_output=1.5

for ARGUMENT in "$@"
do
   KEY=$(echo $ARGUMENT | cut -f1 -d=)
   KEY_LENGTH=${#KEY}
   VALUE="${ARGUMENT:$KEY_LENGTH+1}"
   export "$KEY"="$VALUE"
done

source ${env}
set -xe
set -o pipefail

fit_nmove=${fit_nmove:-$((fit_width/anchor_res))}
model_id=${model_id:-nF${nFactor}.d_${train_width}}
output_id=${output_id:-${model_id}}
hexagon=${hexagon:-${path}/hexagon.d_${train_width}.tsv.gz}
pixel=${pixel:-${path}/filtered.matrix.tsv.gz}

anchor_info=prj_${fit_width}.r_${anchor_res}
radius=$((anchor_res+1))

output_path=${path}/ficture_output/analysis/${model_id}
figure_path=${output_path}/figure2

if [ ! -d "${figure_path}/sub" ]; then
    mkdir -p ${figure_path}/sub
fi

output=${output_path}/${output_id}
model=${output}.model.p

# Transform
output=${output_path}/${output_id}.${anchor_info}
ficture transform --input ${pixel} --output_pref ${output} --model ${model} --key ${key} --major_axis ${major_axis} --hex_width ${fit_width} --n_move ${fit_nmove} --min_ct_per_unit ${min_ct_per_unit_fit} --mu_scale ${mu_scale} --thread ${thread} --precision 2

# Pixel-level decoding
prefix=${output_id}.decode.${anchor_info}_${radius}
input=${path}/batched.matrix.tsv.gz
anchor=${output}.fit_result.tsv.gz
output_decode=${output_path}/${prefix}
topk=3

# Perform pixel-level decoding
ficture slda_decode --input ${input} --output ${output_decode} --model ${model} \
    --anchor ${anchor} --anchor_in_um --neighbor_radius ${radius} \
    --mu_scale ${mu_scale} --key ${key} --precision 0.1 \
    --lite_topk_output_pixel ${topk} --lite_topk_output_anchor ${topk} \
    --thread ${thread}

# Sort pixel output for visualization
input_sort=${output_decode}.pixel.tsv.gz
output_sort=${output_decode}.pixel.sorted.tsv.gz
coor=${path}/coordinate_minmax.tsv

# Read coordinate bounds
while IFS=$'\t' read -r r_key r_val; do
    export "${r_key}"="${r_val}"
done < ${coor}

# Sort and index pixel output
offsetx=${xmin}
offsety=${ymin}
rangex=$(echo "(${xmax} - ${xmin} + 0.5)/1+1" | bc)
rangey=$(echo "(${ymax} - ${ymin} + 0.5)/1+1" | bc)
bsize=2000
scale=100

header="##K=${nFactor};TOPK=3\n##BLOCK_SIZE=${bsize};BLOCK_AXIS=X;INDEX_AXIS=Y\n##OFFSET_X=${offsetx};OFFSET_Y=${offsety};SIZE_X=${rangex};SIZE_Y=${rangey};SCALE=${scale}\n#BLOCK\tX\tY\tK1\tK2\tK3\tP1\tP2\tP3"

(echo -e "${header}" && zcat ${input_sort} | tail -n +2 | \
    perl -slane '$F[0]=int(($F[1]-$offx)/$bsize) * $bsize; 
                 $F[1]=int(($F[1]-$offx)*$scale); 
                 $F[1]=($F[1]>=0)?$F[1]:0; 
                 $F[2]=int(($F[2]-$offy)*$scale); 
                 $F[2]=($F[2]>=0)?$F[2]:0; 
                 print join("\t", @F);' \
    -- -bsize=${bsize} -scale=${scale} -offx=${offsetx} -offy=${offsety} | \
    sort -S 4G -k1,1g -k3,3g ) | bgzip -c > ${output_sort}

tabix -f -s1 -b3 -e3 ${output_sort}
