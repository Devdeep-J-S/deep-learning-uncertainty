from __future__ import absolute_import, division, print_function
from distutils.util import strtobool
from matplotlib import pyplot as plt
from argparse import ArgumentParser
import numpy as np
import sys

from data.synthetic import *
from data.real_data import *
from conformal.quantiles import *
from conformal.TCP import *
from utils.visualize import *
from utils.metrics import *
from utils.base_models import *
import sys 
import six
sys.path.append('./conformal/cqr/')
sys.path.append('./conformal/chr/')
sys.modules['sklearn.externals.six'] = six
from conformal.baselines import *

def to_numpy(T): 
    return T.cpu().detach().numpy()

def run_experiment(model='TCP', data_params={}, delta=0.05, alpha=0.1): 
    dataset_name   = data_params['name']
    dataset_base_path = data_params['base_path']
    params = data_params['params']
    data_out = get_scaled_dataset(dataset_name, dataset_base_path, params=params)
    X_train, y_train = to_numpy(data_out.X_tr[:800]), to_numpy(data_out.y_tr[:800]).squeeze()
    X_calib, y_calib = to_numpy(data_out.X_ca[:800]), to_numpy(data_out.y_ca[:800]).squeeze()
    X_test, y_test   = to_numpy(data_out.X_te), to_numpy(data_out.y_te).squeeze()

    # fit model to proper training set
    data_prop = {'X': X_train, 'y': y_train}
    hp = {'hidden_layer_sizes': [(100,100)],
        'activation': ['relu'],
        'solver': ['adam'],
        'alpha': [.0001],
        'learning_rate': ['adaptive'],
        'learning_rate_init': [1e-3],
        'max_iter': [300]}
    print(f'1] Computing best hyperparameters for MLP.')
    best_hp_prop = hp_selection(data_prop, 
                test_size=0.5, 
                seed=42, 
                model_name='MLP', 
                hp=hp)
    f = Model('MLP', hp=best_hp_prop)
    print(f'2] Fitting MLP on proper training set.')
    f.fit(X_train, y_train)

    # compute residuals on calibration set
    print(f'3] Computing residuals on calibration set.')
    y_pred = f.predict(X_calib)
    y_resid_calib = y_calib - y_pred

    # conformal method
    print(f'4] Running {model}...')
    if model == 'TCP':      
        TCP_model    = TCP_RIF(delta=delta)
        TCP_model.fit(X_calib, y_resid_calib)
        q_TCP_RIF_test, r_TCP_RIF_test = TCP_model.predict(X_test)
        q_lower      = -1 * q_TCP_RIF_test
        q_upper      = q_TCP_RIF_test
    elif model == 'CP': 
        q_conformal = empirical_quantile(y_resid_calib, alpha=alpha)
        q_lower     = -1 * q_conformal * np.ones(X_test.shape[0])
        q_upper     = q_conformal * np.ones(X_test.shape[0])
    elif model == 'CQR': 
        cqr = CQR(alpha=alpha)
        cqr.fit(X_calib, y_resid_calib, frac=0.5)
        q_intervals = cqr.predict(X_test)
        q_lower = q_intervals[:,0]; q_upper = q_intervals[:,1]
    elif model == 'CondHist': 
        if len(X_calib.shape) == 1: 
            n_features = 1
        else: 
            n_features = X_calib.shape[1]
        ch = CondHist(alpha=alpha, n_features=n_features)
        ch.fit(X_calib, y_resid_calib, frac=0.5)
        q_intervals = ch.predict(X_test)
        q_lower = q_intervals[:,0]; q_upper = q_intervals[:,1]
    else: 
        raise ValueError('invalid method specified. must be one of ["CP", "TCP", "CQR", or "CondHist"]')

    return compute_coverage(y_test, q_lower, q_upper)

if __name__ == '__main__': 
    parser = ArgumentParser()
    parser.add_argument('--grand_seed', default=42, type=int, help='meta level seed')
    parser.add_argument('-n', '--n_experiments', default=2, type=int, help='# of experiments to run')
    parser.add_argument('--alpha', default=0.1, type=float, help='level of confidence intervals produced')
    parser.add_argument('--base_path', type=str, default='./data/real_data/')
    parser.add_argument('--save', type=strtobool, default=True)
    parser.add_argument('-d','--datasets', nargs='+', help='list of datasets', required=True) #['meps_19', 'meps_20', 'meps_21'] 
    parser.add_argument('-m','--methods', nargs='+', help='list of methods', required=True) #['TCP', 'CP', 'CQR', 'CondHist']   

    args = parser.parse_args()
    
    meps_19 = dict({'name': 'meps_19', 'base_path': args.base_path, 'params': None})
    meps_20 = dict({'name': 'meps_20', 'base_path': args.base_path, 'params': None})
    meps_21 = dict({'name': 'meps_21', 'base_path': args.base_path, 'params': None})
    real_world_datasets = dict({'meps_19': meps_19, 
                                'meps_20': meps_20, 
                                'meps_21': meps_21})

    grand_seed = args.grand_seed
    n_experiments = args.n_experiments
    np.random.seed(grand_seed)
    seeds = np.random.randint(0,100,size=n_experiments)
    datasets = args.datasets 
    methods  = args.methods
    exp_results = []

    for i in range(n_experiments): 
        for dataset in datasets:
            params = {'seed': seeds[i], 'test_size': 0.15}
            real_world_datasets[dataset]['params'] = params

            for method in methods: 
                marginal_coverage, average_length = run_experiment(model=method, 
                                                data_params=real_world_datasets[dataset],
                                                alpha=args.alpha)
                result = {'exp_num': i, 
                          'dataset': dataset, 
                          'model': method, 
                          'marginal_coverage': marginal_coverage, 
                          'average_length': average_length}
                exp_results.append(result)
    
    R = pd.DataFrame(exp_results)
    print(R)
    import pdb; pdb.set_trace()
    if args.save: 
        R.to_csv('real_world_results.csv', index=False)