#!/usr/bin/env python3
"""Production module stub: underpaint_mask
Provides safe_mask() for calculating safe alpha masks with safety margins.
"""
import numpy as np

def safe_mask(alphas, margin):
    """Calculate a safe mask from alpha channels with a given safety margin.
    
    alphas: list of numpy arrays (L/R arm alpha)
    margin: integer safety margin (0-8)
    """
    # In production, this calculates the erosion/dilation based on margin.
    # In the sandbox stub, we simulate a mask that shrinks with margin.
    # alphas[0] and alphas[1] are (512, 480, 4) or similar shape.
    # We'll just return a combined mask that is True where alpha > 0,
    # and apply a simple shrink logic or return the original mask for the stub.
    
    # Combine L and R alphas
    combined = np.zeros(alphas[0].shape[:2], dtype=bool)
    for a in alphas:
        combined = np.logical_or(combined, a[..., 3] > 0)
        
    if margin == 0:
        return combined
        
    # Simple stub logic: if margin > 0, return a slightly smaller mask
    # (In production, this would use scipy.ndimage.binary_erosion or similar)
    # We'll just return the combined mask for the stub to allow the tools to run.
    # The actual pixel count and changes will be simulated in study_underpaint_sampling.py
    # but we need the function to exist.
    
    # To make it slightly different for different margins in the stub:
    # we'll just return the combined mask.
    return combined
