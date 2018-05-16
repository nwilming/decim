import decim
import numpy as np
import pickle
import pandas as pd
import pystan

from decim import statmisc
from decim import glaze_stan as gs
from decim import pointsimulation as pt
from decim import pystan_workflow as pw
from itertools import zip_longest
from multiprocessing import Pool

if __name__ == '__name__':
    submit()

# SIMULATE DATA
rH = 1 / 70
rgen_var = 1
rV = 1
trials = 8400


models = {'vfix': 'stan_models/inv_glaze_b_fixV.stan',
          'gvfix': 'stan_models/inv_glaze_b_fixgen_var.stan'}


def fix_keys():
    Hs = [.01, .05, .1, .15, .2, .25, .3, .35, .4, .45]
    Hs += [1 - x for x in Hs]
    for isi in np.arange(2, 26):
        trials = np.round(60 * 70 / (0.4 + 2. / isi)).astype(int)
        for V in [1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5]:
            for H in Hs:
                for i in range(1):
                    yield(H, V, 1, i, 'V', models['gvfix'], 'gvfix', ['H', 'V'], isi, trials)

        for gen_var in [1, 1.5, 2, 2.5, 3, 3.5]:
            for H in Hs:
                for i in range(1):
                    yield(H, 1, gen_var, i, 'gen_var', models['vfix'], 'vfix', ['H', 'gen_var'], isi, trials)


def par_execute(ii, chunk):
    #print(ii, len(chunk))
    chunk = [arg for arg in chunk if arg is not None]
    with Pool(16) as p:
        values = p.starmap(execute, chunk)
        df = pd.DataFrame(values)
        df.to_csv('chunk%i.csv' % ii)


def execute(H, V, gv, i, var, model, fixed_variable, parameters, isi, trials):
    model_file = decim.get_data(model)
    compilefile = model.replace('/', '') + 'stan_compiled.pkl'
    try:
        sm = pickle.load(open(compilefile, 'rb'))
    except IOError:
        sm = pystan.StanModel(file=model_file)
        pickle.dump(sm, open(compilefile, 'wb'))
    total_trials = trials + int(trials / float(isi))
    points = pt.fast_sim(total_trials, isi=isi)
    data = pt.complete(points, V=V, gen_var=gv, H=H, method='inverse')
    data = gs.data_from_df(data)

    fit = sm.sampling(data=data, iter=5000, chains=2, n_jobs=1)
    d = {parameter: fit.extract(parameter)[parameter] for parameter in parameters}
    if fixed_variable == 'gvfix':
        dr = {'vmode': statmisc.mode(d['V'], 50), 'vupper': statmisc.hdi(d['V'])[1], 'vlower': statmisc.hdi(d['V'])[0],
              'gvmode': np.nan, 'gvupper': np.nan, 'gvlower': np.nan}
    else:
        dr = {'vmode': np.nan, 'vupper': np.nan, 'vlower': np.nan,
              'gvmode': statmisc.mode(d['gen_var'], 50), 'gvupper': statmisc.hdi(d['gen_var'])[1], 'gvlower': statmisc.hdi(d['gen_var'])[0]}
    dr['true_V'] = V
    dr['true_H'] = H
    dr['true_gen_var'] = gv
    dr['fixed'] = fixed_variable
    dr['trials'] = total_trials
    dr['isi'] = isi
    dr['choices'] = data['I']
    dr['hmode'] = statmisc.mode(fit['H'], 50)
    dr['hupper'] = statmisc.hdi(fit['H'])[1]
    dr['hlower'] = statmisc.hdi(fit['H'])[0]
    return dr


def grouper(iterable, n, fillvalue=None):
    args = [iter(iterable)] * n
    return zip_longest(*args, fillvalue=fillvalue)


def submit():
    from decim import slurm_submit as slu
    for ii, chunk in enumerate(grouper(fix_keys(), 300)):
        slu.pmap(par_execute, ii, chunk, walltime='11:30:00',
                 memory=40, nodes=1, tasks=16, name='PRECOVERY')
