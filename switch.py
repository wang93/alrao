import os
import math
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.nn.parameter import Parameter
from torch.autograd import Variable

from numbers import Number
import pdb

#TODO : Let choose the hyperparameters of the switch !
class Switch(nn.Module):
    """
    This class implements the switch distribution
    """
    def __init__(self, nb_models, theta = .9999, alpha=0.001, save_cl_perf=False):
        super(Switch, self).__init__()

        self.nb_models = nb_models
        self.theta = theta
        self.alpha = alpha
        self.t = 1

        self.save_cl_perf = save_cl_perf
        
        self.register_buffer("logw",
            torch.zeros((2, nb_models), requires_grad=False)
        )
        self.register_buffer("logposterior",
            torch.full((nb_models,), -np.log(nb_models), requires_grad=False)
        )
        self.logw[0].fill_(np.log(theta))
        self.logw[1].fill_(np.log(1 - theta))
        self.logw -= np.log(nb_models)
        
        if self.save_cl_perf:
            self.reset_cl_perf()
            
    def reset_cl_perf(self):
        self.cl_loss = [0 for _ in range(self.nb_models)]
        self.cl_correct = [0 for _ in range(self.nb_models)]
        self.cl_total = 0

    def get_cl_perf(self):
        return [(loss / self.cl_total, corr / self.cl_total) \
                for (loss, corr) in zip(self.cl_loss, self.cl_correct)]
        
    def piT(self, t):
        """
        Reprent the prior pi_t in algorithm 1
        """
        return 1/(t+1) #(1.-self.alpha)
    
    def Supdate(self, lst_logpx, y):
        """
        This implements algorithm 1 in "Catching Up Faster in Bayesian 
        Model Selection and Model Averaging
        """
        if self.save_cl_perf:
            self.cl_total += 1
            for (k, x) in enumerate(lst_logpx):
                self.cl_loss[k] += F.nll_loss(x, y).item()
                self.cl_correct[k] += (torch.max(x, 1)[1]).eq(y.data).sum().item() / y.size()[0]

        
        # px is the tensor of the log probabilities of the mini-batch for each classifier
        logpx = torch.stack([-F.nll_loss(x, y, size_average=True) for x in lst_logpx],
                            dim=0).detach()
        from math import isnan
        if any(isnan(p) for p in logpx):
            stop
        if self.nb_models == 1:
            return None

        self.logw += logpx
        pit = self.piT(self.t)
        logpool = log_sum_exp(self.logw[0]) +  np.log(pit)
        self.logw[0] += np.log(1 - pit)

        addtensor = torch.zeros_like(self.logw)
        addtensor[0].fill_(np.log(self.theta))
        addtensor[1].fill_(np.log(1-self.theta))

        self.logw = log_sum_exp(torch.stack([self.logw,
            addtensor + logpool - np.log(self.nb_models)], dim=0), dim = 0)

        self.logw -= log_sum_exp(self.logw)
        self.logposterior = log_sum_exp(self.logw, dim=0)
        self.t += 1

    def forward(self, lst_logpx):
        return log_sum_exp(torch.stack(lst_logpx,-1) + self.logposterior, dim=-1)
    

def log_sum_exp(tensor, dim=None):
    """Numerically stable implementation of the operation

    tensor.exp().sum(dim, keepdim).log()
    From https://github.com/pytorch/pytorch/issues/2591
    """
    if dim is not None:
        m, _ = torch.max(tensor, dim=dim, keepdim=True)
        tensor0 = tensor - m
        return m.squeeze(dim=dim) + torch.log(torch.sum(torch.exp(tensor0),dim=dim))
    else:
        m = torch.max(tensor)
        sum_exp = torch.sum(torch.exp(tensor - m))
        if isinstance(sum_exp, Number):
            return m + math.log(sum_exp)
        else:
            return m + torch.log(sum_exp)
