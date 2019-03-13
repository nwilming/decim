import decim
import numpy as np
import pickle
import pandas as pd
import pystan
from os.path import join

from decim import statmisc
from decim import glaze_to_stan as gs
from decim import pointsimulation as pt
from itertools import zip_longest, product
from multiprocessing import Pool


models = {'none': 'stan_models/inv_glaze_b.stan',
          'vfix': 'stan_models/inv_glaze_b_fixV.stan',
          'gvfix': 'stan_models/inv_glaze_b_fixgen_var.stan'}

nr_reps = 200


def fix_keys():
    Hs = [1 / 5., 1 / 10., 1 / 20., 1 / 30., 1 / 40, 1 / 50.]
    Vs = [1, 1.5, 2, 2.5, 3, 3.5]
    gvs = [1, 1.5, 2, 2.5]
    isis = [1, 2, 5, 10, 20]
    i = 2
    for strat in ['TRUE', 'FIXED', 'DBLFIT']:
        for _ in range(nr_reps):
            for V, H, isi in product(Vs, Hs, isis):
                yield(strat, H, V, 1, i,  'V', models['gvfix'], 'gvfix',
                      ['H', 'V'], isi, 600)
                i += 1
            for gv, H, isi in product(gvs, Hs, isis):
                yield(strat, H, 1, gv, i, 'V', models['vfix'], 'vfix',
                      ['H', 'gen_var'], isi, 600)
                i += 1
            for V, gv, H, isi in product(Vs, gvs, Hs, isis):
                yield(strat, H, V, gv, i, 'V', models['none'], 'none',
                      ['H', 'V', 'gen_var'], isi, 600)
                i += 1


def par_execute(ii, chunks):
    chunks = [arg for arg in chunks if arg is not None]
    chunks = grouper(chunks, 16)
    results = []
    with Pool(16) as p:
        cnt = 1
        for chunk in chunks:
            chunk = [c for c in chunk if not c is None]
            values = p.starmap(execute_strategy, chunk)
            results.extend(values)
            df = pd.DataFrame(values)
            df.to_hdf(
                '/work/faty014/kobe_param_rec_var_%i.hdf' % (ii),
                key='chunk%i' % cnt)
            cnt += 1


def execute_strategy(strat, H, V, gv, i, var, model, fixed_variable,
                     parameters, isi, duration):
    model_file = decim.get_data(model)
    compilefile = join(
        '/work/faty014', model.replace('/', '') + 'stan_compiled.pkl')
    try:
        sm = pickle.load(open(compilefile, 'rb'))
    except IOError:
        sm = pystan.StanModel(file=model_file)
        pickle.dump(sm, open(compilefile, 'wb'))
    #total_trials = trials + int(trials / float(isi))
    dur = 2.25
    conf = 2
    trials_per_block = (duration /
                        ((dur + conf) * (1 / isi) + (dur * (1 - (1 / isi)))))
    total_trials = int(trials_per_block * 2 * 5)

    print('Total trials: %i'%total_trials)

    Hest = np.nan
    if strat == "TRUE":
        # Infered H is real H
        points = pt.fast_sim(total_trials, tH=H, isi=isi, nodec=0)
        data = pt.complete(points, V=V, gen_var=gv, H=H, method='inverse')
        data = gs.data_from_df(data)
    elif strat == "FIXED":
        # real H is 1/30, infered H is H
        points = pt.fast_sim(total_trials, tH=1 / 30, isi=isi, nodec=0)
        data = pt.complete(points, V=V, gen_var=gv, H=H, method='inverse')
        data = gs.data_from_df(data)
    else:
        # Infered H is based on data
        points = pt.fast_sim(total_trials, tH=H, isi=isi, nodec=0)
        Hest = pt.opt_h(points, gen_var=gv, V=V)
        print('True H: %3.2f, Estimated %3.2f' % (H, Hest))
        data = pt.complete(points, V=V, gen_var=gv, H=Hest, method='inverse')
        data = gs.data_from_df(data)

    fit = sm.sampling(data=data, iter=2500, chains=2, n_jobs=1)
    d = {parameter: fit.extract(parameter)[parameter]
         for parameter in parameters}
    if fixed_variable == 'gvfix':
        dr = {'vmode': statmisc.mode(d['V'], 50),
              'vupper': statmisc.hdi(d['V'])[1],
              'vlower': statmisc.hdi(d['V'])[0],
              'gvmode': np.nan,
              'gvupper': np.nan,
              'gvlower': np.nan}
    elif fixed_variable == 'vfix':
        dr = {'vmode': np.nan,
              'vupper': np.nan,
              'vlower': np.nan,
              'gvmode': statmisc.mode(d['gen_var'], 50),
              'gvupper': statmisc.hdi(d['gen_var'])[1],
              'gvlower': statmisc.hdi(d['gen_var'])[0]}
    else:
        print(list(d.keys()))
        dr = {'vmode': statmisc.mode(d['V'], 50),
              'vupper': statmisc.hdi(d['V'])[1],
              'vlower': statmisc.hdi(d['V'])[0],
              'gvmode': statmisc.mode(d['gen_var'], 50),
              'gvupper': statmisc.hdi(d['gen_var'])[1],
              'gvlower': statmisc.hdi(d['gen_var'])[0]}
    dr['strat'] = strat
    dr['H_est'] = Hest
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
    for ii, chunk in enumerate(grouper(fix_keys(), 1500)):
        slu.pmap(par_execute, ii, chunk, walltime='11:55:00',
                 memory=60, nodes=1, tasks=16, name='PRECOVERY')
# if __name__ == '__main__':
 #   submit()
