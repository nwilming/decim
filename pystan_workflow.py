import pystan
# import stan_utility  # https://github.com/betanalpha/jupyter_case_studies
import pandas as pd
import numpy as np

'''
1. import model and data (e.g. from glaze_stan.py)

2. Compile model: sm = pystan.StanModel(model_code=model)

3. Fit model to Data: fit = sm.sampling(data=data, iter=4000, chains=4)
    -specify iterations, chains, etc....
    -returns: StanFit4model instance ('fit' in the following....)
'''


class fit_result(object):

    def __init__(self, fit, name, parameters):
        '''
        fit: StanFit4model instance, result of stan sampling
        name: 'str', e.g. 'subject_session'
        '''
        self.fit = fit
        self.name = name
        self.parameters = parameters

    def summary(self):
        '''
        Get summary (over all chains) of fit and turn into pandas DataFrame.
        '''
        e = pystan.misc._summary(self.fit)
        self.summary = pd.DataFrame(e['summary'], columns=e['summary_colnames'], index=e['summary_rownames'])

    def samples(self, chainwise=False):
        '''
        Extracts diciotnary with permuted (chains are concatenated and warmup is discarded) sampled distribution of all parameters.

        Chainwise can define parameters, for which samples separately per chain are extracted.
        '''
        self.samples = self.fit.extract()
        self.sample_df = pd.DataFrame({parameter: self.fit[parameter] for parameter in self.parameters})
        if chainwise == True:
            self.chain_samples = {}
            for parameter in self.parameters:
                position = self.summary.reset_index().loc[self.summary.index == parameter].index[0]
                ex = self.fit.extract(permuted=False)
                self.chain_samples[parameter] = ex[:, :, position]
            self.chain_samples = pd.DataFrame(self.chain_samples)

    def to_csv(self, samples=False, chainwise=False):
        '''
        Save as csv...
        '''
        self.summary.to_csv('summary_{}.csv'.format(self.name), index=True)
        if samples == True:
            self.sample_df.to_csv('samples_{}.csv'.format(self.name), index=False)
        if chainwise == True:
            self.chain_samples.to_csv('samples_chain_{}.csv'.format(self.name), index=False)