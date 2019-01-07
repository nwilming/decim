import numpy as np
import pandas as pd
import random

from decim import glaze_model as glaze
from scipy import optimize as opt
from scipy.special import erf
from scipy.special import expit
random.seed()
from scipy.stats import expon
from scipy.stats import norm


# SIMULATE POINT LOCATIONS AND DECISION POINTS

def fast_sim(x, tH=1 / 30, nodec=0, isi=35.):
    """
    Simulates a dataset with x trials and true hazardrate tH. Does so faster.

    nodec = minimum points between decisions. Nodec points are shown, after
    that 'isi' determines decision probability.
    """
    inter_choice_dists = np.cumsum([isi] * x)
    inter_choice_dists = np.array(
        [int(j + nodec + nodec * (np.where(inter_choice_dists == j)[0]))
         for j in inter_choice_dists])  # adds 5 (nodec) points between every decision
    inter_choice_dists = inter_choice_dists[inter_choice_dists < x]

    mus = []
    values = []
    start = random.choice([0.5, -0.5])
    cnt = 0
    while cnt < x:
        i = 1 + int(np.round(expon.rvs(scale=1 / tH)))
        mus.append([start] * i)
        values.append(norm.rvs(start, 1, size=i))
        start *= -1
        cnt += i

    df = pd.DataFrame({'rule': np.concatenate(mus)[:x],
                       'value': np.concatenate(values)[:x]})

    # df.columns = ['rule', 'values']
    df.loc[:, 'message'] = 'GL_TRIAL_LOCATION'
    df.loc[:, 'make_choice'] = False
    df.loc[inter_choice_dists, 'make_choice'] = True
    df.loc[:, 'index'] = np.arange(len(df))
    return df

# FILL IN MISSING INFORMATION


def add_belief(df, H, gen_var=1):
    """
    Computes models belief according to glaze at location trials

    Takes simulated dataframe and hazardrate
    """
    glazes = glaze.belief(df, H, gen_var=gen_var)
    df['belief'] = glazes[0]
    return df


def dec_choice_inv(df, V=1):
    '''
    Chooses at decision trials between 0 ('left') and 1 ('right').

    Based on belief and internal noise V.
    '''
    df.loc[:, 'noisy_belief'] = expit(df.belief / V)
    df = df.fillna(method='ffill')
    df.loc[:, 'choice'] = np.random.rand(len(df))
    df.loc[:, 'choice'] = df.noisy_belief > df.choice
    df.loc[:, 'choice'] = df.choice.astype(float)
    df.loc[df.loc[:, 'make_choice'] == False, 'choice'] = np.nan
    return df


def complete(df, H, gen_var=1, gauss=1, V=1, method='sign'):
    """
    Completes simulated dataframe with message, location, belief, rule and correctness
    """
    return dec_choice_inv(add_belief(df, H, gen_var=gen_var), V=V)


def cer(df, H, gen_var, V):
    """
    Completes simulated dataframe and computes cross entropy error.

    Takes dataframe and hazardrate.
    """
    com = complete(df, H, gen_var=gen_var, V=V, method='inverse')
    actualrule = com.loc[com.make_choice, 'rule'] + 0.5
    modelbelief = expit(com.loc[com.make_choice, 'belief'])
    error = -np.sum(((1 - actualrule) * np.log(1 - modelbelief)) +
                    (actualrule * np.log(modelbelief)))
    return error


def opt_h(df, gen_var, V):
    """
    Returns hazard rate with best cross entropy error.
    """

    def error_function(x):
        return cer(df, x, gen_var, V)
    o = opt.minimize_scalar(error_function,
                            bounds=(0, 1), method='bounded')
    return o.x


def h_iter(I, n, hazardrates, trials=1000):
    """
    Returns numpy matrix containing fitted hazardrates
    for given true hazardrates, iterated n times each.

    Takes number of iterations and hazardrates as a list.
    Saves data in a csv file.
    """
    Ms = []

    for h in hazardrates:
        for i in range(n + 1):
            df = fast_sim(trials, h)
            M, error = opt_h(df)
            true_err = cer(df, h)
            Ms.append({'M': M, 'H': h, 'err': error,
                       'true_error': true_err})
    df = pd.DataFrame(Ms)
    df.loc[:, 'trials'] = trials
    df.to_csv("wt{2}_{0}its{1}hazrates.csv".format(
        I, len(hazardrates), trials))
    return df


__version__ = '2.1'

'''
1.1
changed probability of decision trial to 1/35.
1.1.1
PEP-8 fixes
1.2
added function to compute cross entropy error
added function to calculate optimal model hazardrate
made actual generating hazardrate optional parameter in simulate
2.0
Niklas added fast_sim function to make the modules functionality
considerably faster.
2.1
Size number of inter_change_dist raised to 10 000
Added function to iterate opt_h on a list of tH and an arbitrarily
high number of iterations.
Deleted old simulation functions.
Made the module slightly faster by deleting obsolete functions
calculating correct answers of model.
Readability according to PEP-257
'''

