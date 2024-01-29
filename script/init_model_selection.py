import sys, io, os, gzip, glob, copy, re, time, warnings, pickle, argparse, logging
from collections import defaultdict,Counter
import numpy as np
import pandas as pd

from scipy.sparse import *
from sklearn.preprocessing import normalize
from joblib import Parallel, delayed
from sklearn.decomposition import LatentDirichletAllocation as LDA

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utilt import gen_even_slices, chisq, make_mtx_from_dge
from unit_loader import UnitLoader

parser = argparse.ArgumentParser()
parser.add_argument('--input', type=str, help='')
parser.add_argument('--output', type=str, help='')
parser.add_argument('--nFactor', type=int, help='')
parser.add_argument('--key', type=str, default='gn', help='')
parser.add_argument('--R', type=int, default=5, help='')
parser.add_argument('--epoch_init', type=int, default=1, help='')
parser.add_argument('--epoch', type=int, default=1, help='')
parser.add_argument('--test_split', type=float, default=.5, help='')
parser.add_argument('--thread', type=int, default=1, help='')

parser.add_argument('--log_norm', action='store_true', help='')
parser.add_argument('--log_norm_size_factor', action='store_true', help='')

parser.add_argument('--unit_label', default = 'random_index', type=str, help='Which column to use as unit identifier')
parser.add_argument('--feature_label', default = "gene", type=str, help='Which column to use as feature identifier')
parser.add_argument('--unit_attr', type=str, nargs='+', default=[], help='')
parser.add_argument('--epoch_id_length', type=int, default=2, help='')
parser.add_argument('--min_ct_per_unit', type=int, default=50, help='')
parser.add_argument('--debug', action='store_true', help='')
args = parser.parse_args()

key = args.key
thread = args.thread
R = args.R
K = args.nFactor
b_size = 512
topM = 10
score_feature_min = 100
unit_key = args.unit_label.lower()
unit_attr = [x.lower() for x in args.unit_attr]
gene_key = args.feature_label.lower()
logging.basicConfig(level= getattr(logging, "INFO", None))

feature, brc, mtx_org, ft_dict, bc_dict = make_mtx_from_dge(args.input,\
    min_ct_per_unit = args.min_ct_per_unit, min_ct_per_feature = 50,\
    unit = args.unit_label, key = key)
unit_sum = mtx_org.sum(axis = 1)
unit_sum_mean = np.mean(unit_sum)
size_factor = unit_sum / unit_sum_mean
gene_f = feature.Weight.values

N, M = mtx_org.shape
Ntrain = int(N*args.test_split)
Ntest = N - Ntrain
train_idx = set(np.random.choice(N, Ntrain, replace=False) )
test_idx = set(range(N)) - train_idx
train_idx = sorted(list(train_idx))
test_idx = sorted(list(test_idx))

scale_const = 1
if args.log_norm_size_factor:
    mtx_log_norm = mtx_org / size_factor.reshape((-1, 1))
    mtx_log_norm.data = np.log(mtx_log_norm.data + 1)
    scale_const = np.log(1/np.quantile(size_factor, q=.95) + 1)
    mtx_log_norm.data = mtx_log_norm.data / scale_const
elif args.log_norm:
    mtx_log_norm = normalize(mtx_org, norm = 'l1', axis = 1)
    mtx_log_norm.data = np.log(mtx_log_norm.data + 1)
    scale_const = np.log(1/np.quantile(unit_sum, q=.95) + 1)
    mtx_log_norm.data = mtx_log_norm.data / scale_const
else:
    mtx_log_norm = mtx_org

mtx_log_norm = mtx_log_norm.tocsr()
results = {}
coh_score = []
mtx = mtx_org[test_idx, :].tocsc()
factor_header = list(np.arange(K).astype(str) )
for r in range(R):
    t0 = time.time()
    model = LDA(n_components=K, learning_method='online', batch_size=b_size, total_samples = N, n_jobs = thread, verbose = 0)
    for e in range(args.epoch_init):
        _ = model.partial_fit(mtx_log_norm[train_idx, :])
    score_train = model.score(mtx_log_norm[train_idx, :])/Ntrain
    score_test = model.score(mtx_log_norm[test_idx, :])/Ntest
    logging.info(f"{r}: {score_train:.2f}, {score_test:.2f}")
    theta = model.transform(mtx_log_norm[test_idx, :])
    topk = theta.argmax(axis = 1)
    logging.info(f"{Counter(topk)}")

    info = mtx.T @ theta
    info = pd.DataFrame(info, columns = factor_header)
    info.index = feature.gene.values
    info['gene_tot'] = info[factor_header].sum(axis = 1)
    info.drop(index = info.index[info.gene_tot < score_feature_min], inplace = True)
    total_k = np.array(info[factor_header].sum(axis = 0) )
    total_umi = info[factor_header].sum().sum()
    res = []
    for k, kname in enumerate(factor_header):
        idx_slices = [idx for idx in gen_even_slices(len(info), thread)]
        with Parallel(n_jobs=thread, verbose=0) as parallel:
            result = parallel(delayed(chisq)(kname, \
                        info.iloc[idx, :].loc[:, [kname, 'gene_tot']],\
                        total_k[k], total_umi) for idx in idx_slices)
        res += [item for sublist in result for item in sublist]
    chidf=pd.DataFrame(res,columns=['gene','factor','Chi2','pval','FoldChange','gene_total'])
    chidf["Rank"] = chidf.groupby(by = "factor")["Chi2"].rank(ascending=False)
    chidf.gene_total = chidf.gene_total.astype(int)
    chidf.sort_values(by=['factor','Chi2'],ascending=[True,False],inplace=True)

    score = []
    for k in range(K):
        wd_idx = chidf.loc[chidf.factor.eq(str(k))].gene.iloc[:topM].map(ft_dict).values
        wd_idx = sorted( list(wd_idx), key = lambda x : -gene_f[x])
        s = 0
        for ii in range(topM - 1):
            for jj in range(ii+1, topM):
                i = wd_idx[ii]
                j = wd_idx[jj]
                idx = mtx.indices[mtx.indptr[i]:mtx.indptr[i+1]]
                denom = mtx[:, [i]].toarray()[idx] * gene_f[j] / gene_f[i]
                num = mtx[:, [j]].toarray()[idx]
                s += (theta[idx, k].reshape((-1, 1)) * np.log(num/denom + 1)).sum()
        s0 = s / theta[:, k].sum()
        coh_score.append([r, k, s, s0])
        score.append(s0)

    t1 = time.time() - t0
    t0 = time.time()
    logging.info(f"R={r}, {np.mean(score):.2f}, {np.median(score):.2f}, {t1:.2f}")
    results[r] = {'score_train':score_train, 'score_test':score_test, 'model':model, 'coherence':score}

pickle.dump(results, open(args.output + ".model_selection_candidates.p", 'wb'))
coh_score = pd.DataFrame(coh_score, columns = ["R","K","Score0","Score"])
coh_score.to_csv(args.output + ".coherence.tsv", sep='\t', index = False)
v = coh_score.groupby(by = "R").Score.mean()
v = v.sort_values(ascending = False)

### Further update the selected model
best_r = v.index[0]
model = results[best_r]['model']
epoch = .5
n_unit = 0
chunksize = 2000000
with gzip.open(args.input, 'rt') as rf:
    header = rf.readline().strip().split('\t')
header = [x.lower() for x in header]
adt = {unit_key:str, key:int}
adt.update({x:str for x in unit_attr})
while epoch < args.epoch:
    reader = pd.read_csv(gzip.open(args.input, 'rt'), \
            sep='\t',chunksize=chunksize, skiprows=1, names = header,
            usecols=[unit_key,gene_key,key], dtype=adt)
    batch_obj =  UnitLoader(reader, ft_dict, key, \
        batch_id_prefix=args.epoch_id_length, \
        min_ct_per_unit=args.min_ct_per_unit,
        unit_id=unit_key,unit_attr=[])
    while batch_obj.update_batch(b_size):
        N = batch_obj.mtx.shape[0]
        if args.log_norm_size_factor:
            rsum = batch_obj.mtx.sum(axis = 1) / unit_sum_mean
            mtx = batch_obj.mtx / rsum.reshape((-1, 1))
            mtx.data = np.log(mtx.data + 1) / scale_const
        elif args.log_norm:
            mtx = normalize(batch_obj.mtx, norm='l1', axis=1)
            mtx.data = np.log(mtx.data + 1) / scale_const
        else:
            mtx = batch_obj.mtx
        _ = model.partial_fit(mtx)
        n_unit += N
        if args.debug:
            logl = model.score(mtx) / N
            e = len(batch_obj.batch_id_list)
            logging.info(f"Epoch {e-1}, finished {n_unit} units. batch logl: {logl:.4f}")
        if len(batch_obj.batch_id_list) > args.epoch:
            break
    if args.epoch_id_length > 0:
        epoch += len(batch_obj.batch_id_list)
    else:
        epoch += 1

### Rerun all units once and store results
oheader = ["unit",key,"x","y","topK","topP"]+factor_header
dtp = {'topK':int,key:int,"unit":str}
dtp.update({x:float for x in ['topP']+factor_header})
res_f = args.output+".fit_result.tsv.gz"
nbatch = 0
logging.info(f"Result file {res_f}")
ucol = [unit_key,gene_key,key] + unit_attr
reader = pd.read_csv(gzip.open(args.input, 'rt'), \
        sep='\t',chunksize=chunksize, skiprows=1, names=header, \
        usecols=ucol, dtype=adt)
batch_obj =  UnitLoader(reader, ft_dict, key, \
    batch_id_prefix=args.epoch_id_length, \
    min_ct_per_unit=args.min_ct_per_unit, \
    unit_id=unit_key, unit_attr=unit_attr, train_key=key)
post_count = np.zeros((K, M))
while batch_obj.update_batch(b_size):
    N = batch_obj.mtx.shape[0]
    if args.log_norm_size_factor:
        rsum = batch_obj.mtx.sum(axis = 1) / unit_sum_mean
        mtx = batch_obj.mtx / rsum.reshape((-1, 1))
        mtx.data = np.log(mtx.data + 1) / scale_const
    elif args.log_norm:
        mtx = normalize(batch_obj.mtx, norm='l1', axis=1)
        mtx.data = np.log(mtx.data + 1) / scale_const
    else:
        mtx = batch_obj.mtx
    theta = model.transform(mtx)
    post_count += np.array(theta.T @ batch_obj.mtx)
    brc = pd.concat((batch_obj.brc.reset_index(), \
        pd.DataFrame(theta, columns = factor_header )), axis = 1)
    brc['topK'] = np.argmax(theta, axis = 1).astype(int)
    brc['topP'] = np.max(theta, axis = 1)
    brc = brc.astype(dtp)
    logging.info(f"{nbatch}-th batch with {brc.shape[0]} units")
    mod = 'w' if nbatch == 0 else 'a'
    hdr = True if nbatch == 0 else False
    brc[oheader].to_csv(res_f, sep='\t', mode=mod, float_format="%.4e", index=False, header=hdr, compression={"method":"gzip"})
    nbatch += 1
    if args.epoch_id_length > 0 and len(batch_obj.batch_id_list) > 1:
        break
logging.info(f"Finished ({nbatch})")
out_f = args.output+".posterior.count.tsv.gz"
pd.concat([pd.DataFrame({gene_key: feature.gene.values}),\
           pd.DataFrame(post_count.T, columns = factor_header, dtype='float64')],\
    axis = 1).to_csv(out_f, sep='\t', index=False, float_format='%.2f', compression={"method":"gzip"})

model.feature_names_in_ = feature.gene.values
model.log_norm_scaling_const_ = scale_const
model.unit_sum_mean_ = np.mean(unit_sum)
pickle.dump(model, open(args.output + ".model.p", 'wb'))

out_f = args.output + ".model_matrix.tsv.gz"
pd.concat([pd.DataFrame({gene_key: feature.gene.values }),\
           pd.DataFrame(model.components_.T, columns = factor_header, dtype='float64')], \
    axis = 1).to_csv(out_f, sep='\t', index=False, float_format='%.4e', compression={"method":"gzip"})