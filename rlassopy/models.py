from abc import ABCMeta, abstractmethod

import cvxpy as cp
import numpy as np
import scipy.stats as st
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.utils.validation import check_array, check_is_fitted, check_X_y


class RlassoPenalty:
    def __init__(
        self,
        *,
        post=True,
        sqrt=False,
        fit_intercept=True,
        cov_type="nonrobust",
        x_dependent=False,
        n_corr=5,
        max_iter=2,
        n_sim=5000,
        c=1.1,
        gamma=None,
        zero_tol=1e-4,
        convergence_tol=1e-4,
        solver_opts=None,
    ):
        self.post = post
        self.sqrt = sqrt
        self.fit_intercept = fit_intercept
        self.cov_type = cov_type
        self.x_dependent = x_dependent
        self.n_corr = n_corr
        self.max_iter = max_iter
        self.n_sim = n_sim
        self.c = c
        self.gamma = gamma
        self.zero_tol = zero_tol
        self.convergence_tol = convergence_tol
        self.solver_opts = solver_opts or {}

    def _loadings(self, X, resid, n):

        # TODO Implement cluster robust covariance
        # loadings for sqrt lasso
        if self.sqrt:

            if self.cov_type == "nonrobust":
                psi = np.sqrt(np.mean(X**2, axis=0))

            # heteroscedastic robust case
            elif self.cov_type == "robust" and resid is not None:
                Xe2 = np.einsum("ij, i -> j", X**2, resid**2)
                psi_1 = np.sqrt(Xe2 / n)
                psi_2 = np.sqrt(Xe2 / np.sum(resid**2))
                psi = np.maximum(psi_1, psi_2)
            # clustered
            else:
                raise NotImplementedError(
                    "Cluster robust loadings not \
                                            implemented"
                )

        else:
            if self.cov_type == "nonrobust":
                psi = np.sqrt(np.mean(X**2, axis=0))
            elif self.cov_type == "robust" and resid is not None:

                Xe2 = np.einsum("ij, i -> j", X**2, resid**2)
                psi = np.sqrt(Xe2 / n)

            else:
                raise NotImplementedError(
                    "Cluster robust loadings not \
                                            implemented"
                )

        return np.diag(psi)

    def _penalty(
        self,
        n,
        p,
        *,
        sigma_hat=None,
        X=None,
        psi=None,
    ):

        if self.sqrt:
            pass

        else:
            # homoscedasticity and x-independent case
            if self.cov_type == "nonrobust" and not self.x_dependent:
                assert sigma_hat is not None
                proba = st.norm.ppf(1 - (self.gamma / (2 * p)))
                # homoscedastic/non-robust case
                lambd = 2 * self.c * sigma_hat * np.sqrt(n) * proba

            # homoscedastic and x-dependent case
            elif self.cov_type == "nonrobust" and self.x_dependent:
                sims = np.empty(self.n_sim)
                Xpsi = X @ psi
                for r in range(self.n_sim):
                    g = np.random.normal(size=(n, p))
                    sims[r] = n * np.max(2 * np.abs(np.mean(Xpsi * g, axis=0)))

                lambd = self.c * sigma_hat * np.quantile(sims, 1 - self.gamma)

            # heteroscedastic/cluster robust and x-independent case
            elif self.cov_type in ("robust", "cluster") and not self.x_dependent:

                proba = st.norm.ppf(1 - (self.gamma / (2 * p)))
                # homoscedastic/non-robust case
                lambd = 2 * self.c * np.sqrt(n) * proba

            # heteroscedastic/cluster robust and x-dependent case
            elif self.cov_type == "robust" and self.x_dependent:
                sims = np.empty(self.n_sim)
                Xpsi = X @ psi

                for r in range(self.n_sim):
                    g = np.random.normal(size=(n, p))
                    sims[r] = n * np.max(2 * np.abs(np.mean(Xpsi * g, axis=0)))

        return lambd

    def _cvxpy_solve(self, X, y, lambd, psi, n, post):

        _, p = X.shape

        beta = cp.Variable(p)
        objective = cp.Minimize(self._criterion_function(X, y, beta, lambd, psi, n))
        # define the problem
        prob = cp.Problem(objective)
        # solve the problem
        prob.solve(**self.solver_opts)
        # get fitted coefficients
        beta = beta.value
        # round coefficients to zero if they are below the tolerance
        beta[np.where(np.abs(beta) < self.zero_tol)] = 0.0

        return beta

    @staticmethod
    def _post_ols(beta, X, y):

        nonzero_idx = np.where(beta != 0)[0]
        X_sub = X[:, nonzero_idx]
        post_beta = np.linalg.inv(X_sub.T @ X_sub) @ X_sub.T @ y
        beta[nonzero_idx] = post_beta

        return beta

    def fit(self, X, y):
        # check input
        X, y = check_X_y(X, y)

        # get gamma
        n, p = X.shape

        if self.gamma is None:
            self.gamma = 0.1 / np.sqrt(n)


class RlassoBase(BaseEstimator, RegressorMixin, metaclass=ABCMeta):
    """Base class for RLassso and SqrtRLassso"""

    def __init__(
        self,
        *,
        fit_intercept=True,
        post=True,
        cov_type="nonrobust",
        x_dependent=False,
        n_corr=5,
        max_iter=2,
        n_sim=5000,
        c=1.1,
        gamma=None,
        zero_tol=1e-4,
        convergence_tol=1e-4,
        solver_opts=None,
    ):
        self.fit_intercept = fit_intercept
        self.post = post
        self.cov_type = cov_type
        self.x_dependent = x_dependent
        self.n_corr = n_corr
        self.max_iter = max_iter
        self.n_sim = n_sim
        self.c = c
        self.gamma = gamma
        self.zero_tol = zero_tol
        self.convergence_tol = convergence_tol
        self.solver_opts = solver_opts or {}

    def fit(self, X, y):
        """
        Fit model

        Parameters
        ----------
        X : {array-like, sparse matrix}, shape (n_samples, n_features)
            Design matrix.
        y : ndarray of shape (n_samples,)
            Target vecttor.
        """

        X, y = check_X_y(X, y)

        # Intercept handling and scaling
        if self.fit_intercept:
            # mean center the design matrix
            X = X - X.mean(axis=0)
            y = y - y.mean()

        self.coef_, self.lambd_, self.psi_ = self._rlasso_algorithm(X=X, y=y)

        return self

    def predict(self, X):
        """
        Predict target values for X.

        Parameters
        ----------
        X : {array-like, sparse matrix}, shape (n_samples, n_features)
            Design matrix.

        Returns
        -------
        y : ndarray of shape (n_samples,)
            Predicted target values.
        """
        check_is_fitted(self, "coef_")
        X = check_array(X)

        pred = X @ self.coef_
        if self.fit_intercept:
            pred += self.intercept_

        return pred

    @abstractmethod
    def _rlasso_algorithm(self, X, y, X_hat, y_hat):
        pass

    @abstractmethod
    def _criterion_function(self, X, y):
        pass

    @abstractmethod
    def _penalty_loadings(self, X, y):
        pass

    @abstractmethod
    def _penalty_level(self, X, y):
        pass

    def _cvxpy_solve(self, X, y, lambd, psi, n):

        _, p = X.shape

        beta = cp.Variable(p)
        objective = cp.Minimize(self._criterion_function(X, y, beta, lambd, psi, n))
        # define the problem
        prob = cp.Problem(objective)
        # solve the problem
        prob.solve(**self.solver_opts)
        # get fitted coefficients
        beta = beta.value
        # round coefficients to zero if they are below the tolerance
        beta[np.where(np.abs(beta) < self.zero_tol)] = 0.0

        if self.post:
            # get index of all nonzero coefficients
            nonzero_idx = np.where(beta != 0)[0]
            X_sub = X[:, nonzero_idx]
            post_beta = np.linalg.inv(X_sub.T @ X_sub) @ X_sub.T @ y
            beta[nonzero_idx] = post_beta

        return beta


class Rlasso(RlassoBase):
    def _criterion_function(self, X, y, beta, lambd, psi, n):
        """
        Compute the criterion function for the RLasso algorithm.

        Parameters
        ----------
        X : {array-like, sparse matrix}, shape (n_samples, n_features)
            Design matrix.
        y : ndarray of shape (n_samples,)
            Target vecttor.
        beta : ndarray of shape (n_features,)
            Fitted coefficients.
        lambd : float
            Regularization parameter.
        psi : float
            Penalty parameter.

        Returns
        -------
        criterion : float
            Value of the criterion function.
        """

        loss = cp.sum_squares(y - X @ beta) / n
        reg = (lambd / n) * cp.norm1(psi @ beta)

        return loss + reg

    def _penalty_loadings(self, X, n, resid=None):

        if self.cov_type == "robust" and resid is not None:

            Xe2 = np.einsum("ij, i -> j", X**2, resid**2)
            psi = np.sqrt(Xe2 / n)

        elif self.cov_type == "cluster":
            # TODO Implement cluster robust covariance
            raise NotImplementedError

        # homoscedastic/non-robust case
        else:
            psi = np.sqrt(np.mean(X**2, axis=0))

        return np.diag(psi)

    def _penalty_level(self, n, p, *, sigma_hat=None, X=None, psi=None):

        if self.gamma is None:
            self.gamma = 0.1 / np.log(n)

        if self.x_dependent:
            # TODO: Implement x-dependent penalty level
            sims = np.empty(self.n_sim)
            Xpsi = X @ psi
            if self.cov_type == "nonrobust":

                for r in range(self.n_sim):
                    g = np.random.normal(size=(n, p))
                    sims[r] = n * np.max(2 * np.abs(np.mean(Xpsi * g, axis=0)))

                lambd = self.c * sigma_hat * np.quantile(sims, 1 - self.gamma)

            else:

                pass
                print(f"Lambda: {lambd}")

        # x-independent case
        else:
            prob = st.norm.ppf(1 - (self.gamma / (2 * p)))

            # homoscedastic/non-robust case
            if self.cov_type == "nonrobust" and sigma_hat is not None:
                lambd = 2 * self.c * sigma_hat * np.sqrt(n) * prob
            # heteroscedastic and cluster robust
            else:
                lambd = 2 * self.c * np.sqrt(n) * prob

        return lambd

    def _rlasso_algorithm(self, X, y):

        n, p = X.shape

        r = np.empty(p)
        for k in range(p):
            r[k] = np.abs(st.pearsonr(X[:, k], y)[0])

        X_top = X[:, np.argsort(r)[-self.n_corr :]]
        beta0 = np.linalg.inv(X_top.T @ X_top) @ X_top.T @ y
        resid0 = y - X_top @ beta0

        n_iter = 0
        if self.cov_type == "nonrobust":
            psi = self._penalty_loadings(X=X, n=n)
            lambd0 = 0.0
            for _ in range(self.max_iter):
                sigmahat = np.sqrt(np.mean(resid0**2))
                if self.x_dependent:
                    lambd = self._penalty_level(
                        n=n, p=p, sigma_hat=sigmahat, X=X, psi=psi
                    )
                else:
                    lambd = self._penalty_level(n=n, p=p, sigma_hat=sigmahat)

                if np.isclose(lambd, lambd0, atol=self.convergence_tol):
                    break
                else:
                    beta0 = self._cvxpy_solve(
                        X=X,
                        y=y,
                        lambd=lambd,
                        psi=psi,
                        n=n,
                    )
                    resid0 = y - X @ beta0
                    lambd0 = lambd
                    n_iter += 1
            lambd = lambd0

        else:
            lambd = self._penalty_level(n=n, p=p)
            psi0 = np.diag(np.ones(p))
            for _ in range(self.max_iter):
                psi = self._penalty_loadings(X=X, n=n, resid=resid0)

                if np.allclose(psi, psi0, atol=self.convergence_tol):
                    break
                else:
                    beta0 = self._cvxpy_solve(
                        X=X,
                        y=y,
                        lambd=lambd,
                        psi=psi,
                        n=n,
                    )
                    resid0 = y - X @ beta0
                    psi0 = psi
                    n_iter += 1
            psi = psi0

        beta = beta0

        return beta, lambd, psi


class SqrtRlasso(RlassoBase):
    def _criterion_function(self, X, y, beta, lambd, psi, n):
        """
        Compute the criterion function for the RLasso algorithm.

        Parameters
        ----------
        X : {array-like, sparse matrix}, shape (n_samples, n_features)
            Design matrix.
        y : ndarray of shape (n_samples,)
            Target vecttor.
        beta : ndarray of shape (n_features,)
            Fitted coefficients.
        lambd : float
            Regularization parameter.
        psi : float
            Penalty parameter.

        Returns
        -------
        criterion : float
            Value of the criterion function.
        """

        loss = cp.norm2(y - X @ beta) / cp.sqrt(n)
        reg = (lambd / n) * cp.norm1(psi @ beta)

        return loss + reg

    def _penalty_level(self, n, p):

        if self.gamma is None:
            self.gamma = 0.1 / np.log(n)

        prob = st.norm.ppf(1 - (self.gamma / (2 * p)))

        if self.x_dependent:
            raise NotImplementedError("x-dependent penalty not implemented")
        else:
            lambd = self.c * np.sqrt(n) * prob

        return lambd

    def _penalty_loadings(self, X, n, *, resid=None):
        # homonoscadstic case
        if self.cov_type == "nonrobust":
            psi = np.sqrt(np.mean(X**2, axis=0))

        # heteroscedastic robust case
        elif self.cov_type == "robust" and resid is not None:
            Xe2 = np.einsum("ij, i -> j", X**2, resid**2)
            psi_1 = np.sqrt(Xe2 / n)
            psi_2 = np.sqrt(Xe2 / np.sum(resid**2))
            psi = np.maximum(psi_1, psi_2)
        # clustered
        else:
            raise NotImplementedError(
                "Cluster robust loadings not \
                                        implemented"
            )
        return np.diag(psi)

    def _rlasso_algorithm(self, X, y):

        n, p = X.shape

        if self.cov_type == "nonrobust":

            self.n_iter_ = None
            lambd = self._penalty_level(n=n, p=p)
            psi = self._penalty_loadings(X=X, n=n)
            beta = self._cvxpy_solve(
                X=X,
                y=y,
                lambd=lambd,
                psi=psi,
                n=n,
            )
            return beta, lambd, psi

        else:

            r = np.empty(p)
            for k in range(p):
                r[k] = np.abs(st.pearsonr(X[:, k], y)[0])

            X_top = X[:, np.argsort(r)[-self.n_corr :]]
            beta0 = np.linalg.inv(X_top.T @ X_top) @ X_top.T @ y
            resid0 = y - X_top @ beta0
            self.n_iter_ = 0

            lambd = self._penalty_level(n=n, p=p)
            psi0 = np.diag(np.ones(p))
            for _ in range(self.max_iter):
                psi = self._penalty_loadings(X=X, n=n, resid=resid0)

                if np.allclose(psi, psi0, atol=self.convergence_tol):
                    break
                else:
                    beta0 = self._cvxpy_solve(
                        X=X,
                        y=y,
                        lambd=lambd,
                        psi=psi,
                        n=n,
                    )
                    resid0 = y - X @ beta0
                    psi0 = psi
                    self.n_iter_ += 1
            psi = psi0
            beta = beta0

            return beta, lambd, psi
