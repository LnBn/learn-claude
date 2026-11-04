# Notation

Every course, quiz, exam, interview and drill uses this notation. Where a book differs, the lesson says so once in a `[!notation]` callout. Edit this sheet to change a convention.

## General

| Symbol | Meaning |
|---|---|
| $x, y, a$ | scalars (italic lowercase) |
| $\mathbf{x}, \mathbf{y}$ | vectors (bold lowercase), always column vectors |
| $\mathbf{A}, \mathbf{X}$ | matrices (bold uppercase) |
| $\mathbf{A}^\top$ | transpose |
| $\mathbf{x}^\top \mathbf{y}$ | inner product; $\lVert \mathbf{x} \rVert$ is the Euclidean norm |
| $\mathbf{I}_n$ | the $n \times n$ identity; $\mathbf{I}$ when the size is clear |
| $\log$ | natural logarithm |
| $\mathbb{1}\{A\}$ | indicator of the event $A$ |

## Linear algebra

| Symbol | Meaning |
|---|---|
| $\operatorname{tr}(\mathbf{A})$, $\det(\mathbf{A})$, $\operatorname{rank}(\mathbf{A})$ | trace, determinant, rank |
| $C(\mathbf{A})$, $N(\mathbf{A})$ | column space, nullspace |
| $\lambda_i$, $\mathbf{v}_i$ | eigenvalues, eigenvectors: $\mathbf{A}\mathbf{v}_i = \lambda_i \mathbf{v}_i$ |
| $\mathbf{A} = \mathbf{Q}\boldsymbol\Lambda\mathbf{Q}^\top$ | spectral decomposition of a symmetric $\mathbf{A}$ ($\mathbf{Q}$ orthogonal) |
| $\mathbf{A} = \mathbf{U}\boldsymbol\Sigma\mathbf{V}^\top$ | singular value decomposition, singular values $\sigma_1 \ge \sigma_2 \ge \dots \ge 0$ |
| $\mathbf{P}$ | a projection matrix |
| $\mathbf{A} \succ 0$, $\mathbf{A} \succeq 0$ | positive definite, positive semidefinite |

## Probability

| Symbol | Meaning |
|---|---|
| $X, Y$ | random variables (uppercase); $x, y$ their values |
| $\mathbf{X} = (X_1, \dots, X_n)^\top$ | a random vector, when one is needed (in regression $\mathbf{X}$ is the design matrix instead; the lesson says which) |
| $P(A)$, $P(A \mid B)$ | probability, conditional probability |
| $F_X$, $f_X$, $p_X$ | CDF, PDF, PMF of $X$ (subscript dropped when clear) |
| $\mathbb{E}[X]$, $\operatorname{Var}(X)$, $\operatorname{Cov}(X, Y)$, $\operatorname{Corr}(X, Y)$ | expectation, variance, covariance, correlation |
| $\mathbb{E}[X \mid Y]$ | conditional expectation (a random variable); $\mathbb{E}[X \mid Y = y]$ is a number |
| $M_X(t)$ | moment generating function $\mathbb{E}[e^{tX}]$ |
| $X \perp Y$ | independent |
| $X_1, \dots, X_n \overset{\text{iid}}{\sim} F$ | independent and identically distributed |
| $X_{(1)} \le \dots \le X_{(n)}$ | order statistics |
| $\Phi$, $\varphi$ | standard normal CDF and PDF |
| $\xrightarrow{p}$, $\xrightarrow{d}$ | convergence in probability, in distribution |

### Distributions

| Notation | Support | Mean | Variance |
|---|---|---|---|
| $\mathrm{Bern}(p)$ | $\{0, 1\}$ | $p$ | $p(1-p)$ |
| $\mathrm{Bin}(n, p)$ | $\{0, \dots, n\}$ | $np$ | $np(1-p)$ |
| $\mathrm{Geom}(p)$: failures before the first success | $\{0, 1, \dots\}$ | $(1-p)/p$ | $(1-p)/p^2$ |
| $\mathrm{FS}(p)$: trials up to and including the first success | $\{1, 2, \dots\}$ | $1/p$ | $(1-p)/p^2$ |
| $\mathrm{Pois}(\lambda)$ | $\{0, 1, \dots\}$ | $\lambda$ | $\lambda$ |
| $\mathrm{Unif}(a, b)$ | $[a, b]$ | $(a+b)/2$ | $(b-a)^2/12$ |
| $\mathcal{N}(\mu, \sigma^2)$, second argument the **variance** | $\mathbb{R}$ | $\mu$ | $\sigma^2$ |
| $\mathrm{Expo}(\lambda)$, $\lambda$ the **rate** | $[0, \infty)$ | $1/\lambda$ | $1/\lambda^2$ |
| $\mathrm{Gamma}(a, \lambda)$, $\lambda$ the **rate** | $[0, \infty)$ | $a/\lambda$ | $a/\lambda^2$ |
| $\mathrm{Beta}(a, b)$ | $[0, 1]$ | $a/(a+b)$ | $\dfrac{ab}{(a+b)^2(a+b+1)}$ |
| $\chi^2_k$ | $[0, \infty)$ | $k$ | $2k$ |
| $\mathcal{N}_k(\boldsymbol\mu, \boldsymbol\Sigma)$ | $\mathbb{R}^k$ | $\boldsymbol\mu$ | $\boldsymbol\Sigma$ (covariance matrix) |

Books that differ: Wasserman writes $\mathrm{Exp}(\beta)$ and $\mathrm{Gamma}(\alpha, \beta)$ with $\beta$ a **scale** (mean $\beta$ for the exponential), so his $\beta$ is $1/\lambda$ here.

## Statistics

| Symbol | Meaning |
|---|---|
| $\theta$, $\hat\theta$ | a parameter, an estimator of it ($\hat\theta_n$ when the sample size matters) |
| $\bar X_n$ | sample mean $\frac{1}{n}\sum_{i=1}^n X_i$ |
| $S_n^2$ | sample variance with divisor $n-1$ |
| $\operatorname{bias}(\hat\theta)$, $\operatorname{se}(\hat\theta)$, $\widehat{\operatorname{se}}$ | bias, standard error, estimated standard error |
| $\operatorname{MSE}(\hat\theta)$ | mean squared error $= \operatorname{bias}^2 + \operatorname{Var}$ |
| $L(\theta)$, $\ell(\theta)$ | likelihood, log-likelihood |
| $\hat\theta_{\text{MLE}}$ | maximum likelihood estimator |
| $I(\theta)$, $I_n(\theta)$ | Fisher information of one observation, of $n$ |
| $H_0$, $H_1$, $\alpha$ | null and alternative hypotheses, test size |
| $z_{\alpha/2}$ | the value with $P(Z > z_{\alpha/2}) = \alpha/2$ for $Z \sim \mathcal{N}(0,1)$ |

### Regression

| Symbol | Meaning |
|---|---|
| $\mathbf{y} = \mathbf{X}\boldsymbol\beta + \boldsymbol\varepsilon$ | linear model: $\mathbf{y}$ is $n \times 1$, $\mathbf{X}$ the $n \times p$ design matrix, $\boldsymbol\beta$ the $p \times 1$ coefficients |
| $\hat{\boldsymbol\beta} = (\mathbf{X}^\top\mathbf{X})^{-1}\mathbf{X}^\top\mathbf{y}$ | OLS estimator |
| $\hat{\mathbf{y}} = \mathbf{H}\mathbf{y}$, $\mathbf{H} = \mathbf{X}(\mathbf{X}^\top\mathbf{X})^{-1}\mathbf{X}^\top$ | fitted values, hat matrix |
| $\hat{\boldsymbol\varepsilon} = \mathbf{y} - \hat{\mathbf{y}}$ | residuals |
| $\beta_0$, $\beta_1$ | intercept and slope in simple regression $Y_i = \beta_0 + \beta_1 x_i + \varepsilon_i$ |
| $R^2$ | coefficient of determination |
