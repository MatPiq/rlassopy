import numpy as np
import pytest
from numpy.testing import assert_allclose, assert_array_equal
from statsmodels.regression.linear_model import OLS

from rlassopy import Rlasso


def data():
    """
    Data-generating function following Belloni (2011).
    """
    np.random.seed(234923)

    # Based on the example in the Belloni paper
    n = 100
    p = 500
    ii = np.arange(p)
    cx = 0.5 ** np.abs(np.subtract.outer(ii, ii))
    cxr = np.linalg.cholesky(cx)

    X = np.dot(np.random.normal(size=(n, p)), cxr.T)
    b = np.zeros(p)
    b[0:5] = [1, 1, 1, 1, 1]
    y = np.dot(X, b) + 0.25 * np.random.normal(size=n)

    return X, y, b, cx


def test_rlasso_oracle():
    """
    Same test as `statsmodels.regression.tests_regression.test_sqrt_lasso`
    with addition of test for selected components.
    Based on SQUARE-ROOT LASSO: PIVOTAL RECOVERY OF SPARSE
    SIGNALS VIA CONIC PROGRAMMING, Belloni (2011), p.10.
    """
    X, y, b, cx = data()
    _, p = X.shape

    # Empirical risk ratio.
    expected_oracle = {False: 3, True: 1}

    # Used for regression testing
    expected_params = {
        False: np.r_[0.86706825, 1.00475367, 0.98628392, 0.93160201, 0.9293992],
        True: np.r_[0.95300153, 1.03060962, 1.01297103, 0.97404348, 1.00306961],
    }

    for post in False, True:

        res = Rlasso(sqrt=False, post=post).fit(X, y)
        e = res.coef_ - b
        numer = np.sqrt(np.dot(e, np.dot(cx, e)))

        oracle = OLS(y, X[:, 0:5]).fit()
        oracle_err = np.zeros(p)
        oracle_err[0:5] = oracle.params - b[0:5]
        denom = np.sqrt(np.dot(oracle_err, np.dot(cx, oracle_err)))

        # Check performance relative to oracle, should be around 3.5 for
        # post=False, 1 for post=True
        assert_allclose(numer / denom, expected_oracle[post], rtol=0.5, atol=0.1)

        # Check number of selected components relative to oracle,
        # should be equal for small noise lvls
        n_components = np.nonzero(res.coef_)[0].size
        assert n_components == 5

        # Regression test the parameters
        assert_allclose(res.coef_[0:5], expected_params[post], rtol=1e-5, atol=1e-5)


def test_sqrt_rlasso_oracle():
    """
    Same as `test_rlasso_oracle` but with sqrt=True.
    Note empirical risk ratio is 3.5 and
    different from `test_rlasso_oracle`.
    """
    X, y, b, cx = data()
    _, p = X.shape

    # Empirical risk ratio. Note: statsmodels uses
    # 3.0, this should be 3.5 (see the paper)
    expected_oracle = {False: 3.5, True: 1}

    # Used for regression testing
    expected_params = {
        False: np.r_[0.83636403, 0.98917002, 0.9913215, 0.90954702, 0.90655144],
        True: np.r_[0.95300153, 1.03060962, 1.01297103, 0.97404348, 1.00306961],
    }

    for post in False, True:

        res = Rlasso(sqrt=True, post=post).fit(X, y)
        e = res.coef_ - b
        numer = np.sqrt(np.dot(e, np.dot(cx, e)))

        oracle = OLS(y, X[:, 0:5]).fit()
        oracle_err = np.zeros(p)
        oracle_err[0:5] = oracle.params - b[0:5]
        denom = np.sqrt(np.dot(oracle_err, np.dot(cx, oracle_err)))

        # Check performance relative to oracle, should be around 3.5 for
        # post=False, 1 for post=True
        assert_allclose(numer / denom, expected_oracle[post], rtol=0.5, atol=0.1)

        # Check number of selected components relative to oracle,
        # should be equal for small noise lvls
        n_components = np.nonzero(res.coef_)[0].size
        assert n_components == 5

        # Regression test the parameters
        assert_allclose(res.coef_[0:5], expected_params[post], rtol=1e-5, atol=1e-5)