"""Opaque sleeve coverage and conservative Chebyshev-pixel erosion.

Erode each arm separately before union: a pixel is safe only if a whole
(2r+1) square is fully opaque in at least one arm. This is a geometric margin,
not a promise that arbitrary rendering scales or transforms will be identical.
"""
import numpy as np


def safe_mask(arms, margin=0):
    if not isinstance(margin, int) or isinstance(margin, bool) or not 0 <= margin <= 8:
        raise ValueError('margin must be an integer from 0 through 8')
    if not arms:
        raise ValueError('no arms')
    shape = arms[0].shape
    if len(shape) != 2 or any(a.shape != shape for a in arms):
        raise ValueError('alpha dimensions differ')
    union = np.zeros(shape,dtype=bool)
    h,w=shape
    for alpha in arms:
        opaque = np.asarray(alpha) == 255
        padded = np.pad(opaque,margin,mode='constant',constant_values=False)
        eroded = np.ones(shape,dtype=bool)
        for dy in range(2*margin+1):
            for dx in range(2*margin+1):
                eroded &= padded[dy:dy+h,dx:dx+w]
        union |= eroded
    return union
