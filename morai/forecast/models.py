"""Creates models for forecasting mortality rates."""
import numpy as np
import pandas as pd
import plotly.express as px
import statsmodels.api as sm
import statsmodels.formula.api as smf

from morai.utils import custom_logger

logger = custom_logger.setup_logging(__name__)


class GLM:
    """Create a GLM model."""

    def __init__(
        self,
        X,
        y,
        weights=None,
        r_style=False,
        mapping=None,
    ):
        """
        Initialize the model.

        Parameters
        ----------
        X : pd.DataFrame
            The features
        y : pd.Series
            The target
        weights : pd.Series, optional
            The weights
        r_style : bool, optional
            Whether to use R-style formulas
        mapping : dict, optional
            The mapping of the features to the encoding and only needed
            if r_style is True

        """
        logger.info("initialzed GLM and add constant to X")
        self.X = sm.add_constant(X)
        self.y = y
        self.weights = weights
        self.model = None
        self.r_style = r_style
        self.mapping = mapping

    def fit_model(self, family=None, **kwargs):
        """
        Fit the GLM model.

        Returns
        -------
        model : GLM
            The GLM model
        Family : sm.families
            The family
        kwargs : dict
            Additional keyword arguments

        """
        X = self.X
        y = self.y
        weights = self.weights
        if family is None:
            family = sm.families.Binomial()
        logger.info(f"fitting GLM model with statsmodels and {family} family...")

        # using either r-style or python-style formula
        if self.r_style:
            model_data = pd.concat([y, X], axis=1)
            formula = self.get_formula()
            model = smf.glm(
                formula=formula,
                data=model_data,
                family=family,
                freq_weights=weights,
                **kwargs,
            ).fit()
        else:
            model = sm.GLM(
                endog=y,
                exog=X,
                family=sm.families.Binomial(),
                freq_weights=weights,
                **kwargs,
            ).fit()

        self.model = model

        return model

    def get_formula(self):
        """
        Get the formula for the GLM model.

        Returns
        -------
        formula : str
            The formula

        """
        y = self.y
        X = self.X
        # creating formula that uses categories and passthrough
        if self.mapping:
            cat_pass_keys = {
                key: value
                for key, value in self.mapping.items()
                if value["type"] == "cat_pass"
            }
            other_keys = {
                key: value
                for key, value in self.mapping.items()
                if value["type"] != "cat_pass"
            }
            non_categorical_part = " + ".join(other_keys) if other_keys else ""
            categorical_part = (
                " + ".join([f"C({key})" for key in cat_pass_keys])
                if cat_pass_keys
                else ""
            )

            if non_categorical_part and categorical_part:
                formula = f"{y.name} ~ {non_categorical_part} + {categorical_part}"
            elif non_categorical_part:
                formula = f"{y.name} ~ {non_categorical_part}"
            elif categorical_part:
                formula = f"{y.name} ~ {categorical_part}"
            else:
                formula = f"{y.name} ~ 1"
        else:
            formula = f"{y.name} ~ {' + '.join(X.columns)}"

        logger.info(f"using R-style formula: {formula}")

        return formula

    def get_odds(self, display=False):
        """
        Get the odds ratio.

        Parameters
        ----------
        display : bool, optional
            Whether to display the odds ratio

        Returns
        -------
        odds_ratio : pd.DataFrame
            The odds ratio

        """
        if self.model is None:
            raise ValueError("model is not fitted use get_model method")

        model = self.model

        logger.info("generating odds ratio from model")
        odds_ratio = np.exp(model.params)

        # displaying chart of odds ratio
        if display:
            coef_df = pd.DataFrame(
                {"feature": model.params.index[1:], "coefficient": model.params[1:]}
            )
            coef_df = coef_df.sort_values("coefficient", ascending=False)

            odds_ratio = px.bar(
                coef_df,
                x="feature",
                y="coefficient",
                title="Feature Importance",
                labels={"coefficient": "Coefficient Value", "feature": "Features"},
            )

        return odds_ratio


class LeeCarter:
    """
    Create a Lee Carter model.

    reference:
    - https://en.wikipedia.org/wiki/Lee%E2%80%93Carter_model
    """

    def __init__(
        self,
        age_col="attained_age",
        year_col="observation_year",
        actual_col="death_claim_amount",
        expose_col="amount_exposed",
    ):
        """
        Initialize the model.

        Parameters
        ----------
        age_col : str, optional
            The column name for the attained age
        year_col : str, optional
            The column name for the observation year
        actual_col : str, optional
            The column name for the actual values
        expose_col : str, optional
            The column name for the exposure values

        """
        logger.info("initialized LeeCarter")
        self.age_col = age_col
        self.year_col = year_col
        self.actual_col = actual_col
        self.expose_col = expose_col
        # calculations
        self.a_x = None
        self.k_t = None
        self.b_x = None
        self.b_x_k_t = None
        self.lc_df = None
        # forecast
        self.k_t_i = None

    def structure_df(
        self,
        df,
    ):
        """
        Structure the data for the Lee Carter model.

        The Lee Carter model requires the data to be grouped by the attained
        age and observation year. The mortality rates are then calculated.

        Parameters
        ----------
        df : pd.DataFrame
            A DataFrame containing the data to structure.

        Returns
        -------
        lc_df : pd.DataFrame
            lee carter data frame with qx_raw rates

        """
        # check if columns are in the dataframe
        cols_needed = [self.age_col, self.year_col, self.actual_col, self.expose_col]
        missing_cols = [col for col in cols_needed if col not in df.columns]
        if missing_cols:
            raise ValueError(
                f"Missing columns in DataFrame: {', '.join(missing_cols)}. "
                f"Use LeeCarter(age_col, year_col, actual_col, expose_col) "
                f"to specify columns."
            )

        # grouping the data
        logger.info("grouping data by age and year")
        lc_df = (
            df.groupby([self.age_col, self.year_col], observed=True)[
                [self.actual_col, self.expose_col]
            ]
            .sum()
            .reset_index()
        )
        logger.info("calculating qx_raw rates")
        lc_df["qx_raw"] = np.where(
            lc_df[self.actual_col] == 0,
            0,
            lc_df[self.actual_col] / lc_df[self.expose_col],
        )
        logger.info(
            f"there were {len(lc_df[lc_df['qx_raw']>1])} rates "
            f"over 1 that were capped."
        )
        lc_df["qx_raw"] = lc_df["qx_raw"].clip(upper=1)
        self.lc_df = lc_df
        logger.info(f"crude_df shape: {self.lc_df.shape}")

        return self.lc_df

    def fit(self, lc_df):
        """
        Fit the LeeCarter model from a crude_df which will add the qx_lc rates.

        Parameters
        ----------
        lc_df : pd.DataFrame
            A DataFrame containing crude mortality rates for a given population.
            - rows: year
            - columns: age

        Returns
        -------
        lc_df : pd.DataFrame
            A DataFrame containing the LeeCarter mortality rates.

        """
        # checks if models have data needed
        if self.year_col not in lc_df.columns or self.age_col not in lc_df.columns:
            raise ValueError(f"{self.age_col} and {self.year_col} are required")

        # initialize the variables
        logger.info("creating Lee Carter model with qx_raw rates...")
        crude_pivot = lc_df.pivot(
            index=self.year_col, columns=self.age_col, values="qx_raw"
        )

        year_start = crude_pivot.index.min()
        year_end = crude_pivot.index.max()
        age_start = int(crude_pivot.columns.min())
        age_end = int(crude_pivot.columns.max())

        logger.info(f"age range: {age_start}, {age_end}")
        logger.info(f"year range: {year_start}, {year_end}")

        # qx is the mortality matrix
        log_qx = np.log(crude_pivot)

        # ax is the age effect (average mortality rate by age)
        logger.debug("calculating a_x")
        a_x = log_qx.mean(axis=0)
        self.a_x = a_x

        # kt is the time trend
        logger.debug("calculating k_t")
        self.k_t = (log_qx - self.a_x).sum(axis=1)
        e1 = (log_qx - self.a_x).multiply(self.k_t, axis="index")
        e2 = e1.sum(axis=0)
        e3 = self.k_t**2
        e4 = e3.sum()

        # bx is the rate of change of age due to time trend
        logger.debug("calculating b_x")
        b_x = e2 / e4
        self.b_x = b_x

        # matrix multiply for b_x_k_t
        logger.debug("calculating b_x_k_t")
        b_x_k_t = pd.DataFrame(np.outer(self.b_x, self.k_t))
        b_x_k_t = b_x_k_t.transpose()
        b_x_k_t.index = crude_pivot.index
        b_x_k_t.columns = crude_pivot.columns
        self.b_x_k_t = b_x_k_t

        # calculate qx_lc
        logger.info("calculating qx_lc = exp(a_x + b_x * k_t)")
        qx_log_lc = a_x.values + b_x_k_t.values
        qx_log_lc = pd.DataFrame(
            qx_log_lc, index=crude_pivot.index, columns=crude_pivot.columns
        )
        qx_lc = np.exp(qx_log_lc)

        # adding predictions to lc_df
        logger.info("adding qx_lc to lc_df")
        lc_df = pd.merge(
            lc_df,
            qx_lc.reset_index().melt(
                id_vars=self.year_col, var_name=self.age_col, value_name="qx_lc"
            ),
            on=[self.year_col, self.age_col],
            how="left",
        ).astype({self.age_col: "int32", self.year_col: "int32"})
        self.lc_df = lc_df

        return lc_df

    def forecast(self, years):
        """
        Forecast the mortality rates using deterministic random walk.

        Parameters
        ----------
        years : int
            The amount of years to forecast LeeCarter model

        Returns
        -------
        lcf_df : pd.DataFrame
            A DataFrame containing the forecasted LeeCarter mortality rates.

        """
        # checks if models have data needed
        if self.lc_df is None:
            raise ValueError(
                "model is not fitted use fit method please use fit() method"
            )

        # initialize the variables
        variance = 0
        year_cols = list(range(self.k_t.index[-1] + 1, self.k_t.index[-1] + years + 1))

        logger.info("forecasting qx_lc using deterministic random walk...")
        # average change in k_t
        mu = (self.k_t.iloc[-1] - self.k_t.iloc[0]) / len(self.k_t)

        # random walk
        rng = np.random.default_rng()
        k_t_i = (
            self.k_t.iloc[-1]
            + mu * np.arange(1, years + 1)
            + rng.normal(scale=variance, size=years)
        )
        self.k_t_i = k_t_i

        # qx_lc forecast
        b_x_k_t_i = pd.DataFrame(np.outer(self.b_x, k_t_i))
        b_x_k_t_i = b_x_k_t_i.transpose()
        qx_log_lc = self.a_x.values + b_x_k_t_i.values
        qx_lc = np.exp(qx_log_lc)

        # dataframe with forecast
        lcf_df = pd.DataFrame(
            qx_lc,
            index=year_cols,
            columns=self.b_x_k_t.columns,
        )
        lcf_df.index.name = self.year_col
        lcf_df.reset_index().melt(
            id_vars=self.year_col, var_name=self.age_col, value_name="qx_lc"
        )

        return lcf_df

    def map(self, df, age_col=None, year_col=None):
        """
        Map the mortality rates from the Lee Carter model.

        Parameters
        ----------
        df : pd.DataFrame
            A DataFrame containing the data to predict.
        age_col : str, optional
            The column name for the attained age
        year_col : str, optional
            The column name for the observation year

        Returns
        -------
        lc_df : pd.DataFrame
            A DataFrame containing the predicted mortality rates.

        """
        if age_col is None:
            age_col = self.age_col
        if year_col is None:
            year_col = self.year_col
        lc_df = self.lc_df

        # checks if models have data needed
        if lc_df is None:
            raise ValueError(
                "model is not fitted use fit method please use fit() method"
            )
        if year_col not in lc_df.columns or age_col not in lc_df.columns:
            raise ValueError(f"{age_col} and {year_col} are required")

        # map rates to df
        logger.info("mapping qx_lc to df")
        lc_df = lc_df.rename(columns={self.age_col: age_col, self.year_col: year_col})
        lc_df = pd.merge(
            df,
            lc_df[[age_col, year_col, "qx_lc"]],
            on=[age_col, year_col],
            how="left",
            suffixes=("_old", ""),
        )
        if "qx_lc_old" in lc_df.columns:
            lc_df.drop(columns=["qx_lc_old"], inplace=True)

        return lc_df


class CBD:
    """
    Create a Cairns, Blake, Dowd model.

    reference:
    - https://www.actuaries.org/AFIR/Colloquia/Rome2/Cairns_Blake_Dowd.pdf
    """

    def __init__(
        self,
        age_col="attained_age",
        year_col="observation_year",
        actual_col="death_claim_amount",
        expose_col="amount_exposed",
    ):
        """
        Initialize the model.

        Parameters
        ----------
        age_col : str, optional
            The column name for the attained age
        year_col : str, optional
            The column name for the observation year
        actual_col : str, optional
            The column name for the actual values
        expose_col : str, optional
            The column name for the exposure values

        """
        logger.info("initialized CBD")
        self.age_col = age_col
        self.year_col = year_col
        self.actual_col = actual_col
        self.expose_col = expose_col
        # calculations
        self.age_diff = None
        self.ages = None
        self.k_t_1 = None
        self.k_t_2 = None
        self.cbd_df = None
        # forecast
        self.k_1_f = None
        self.k_2_f = None

    def structure_df(
        self,
        df,
    ):
        """
        Structure the data for the CBD model.

        The CBD model requires the data to be the mortality rates with
        the columns as the attained age and the rows as the observation year.

        Parameters
        ----------
        df : pd.DataFrame
            A DataFrame containing the data to structure.

        Returns
        -------
        cbd_df : pd.DataFrame
            CBD data frame

        """
        # check if columns are in the dataframe
        cols_needed = [self.age_col, self.year_col, self.actual_col, self.expose_col]
        missing_cols = [col for col in cols_needed if col not in df.columns]
        if missing_cols:
            raise ValueError(
                f"Missing columns in DataFrame: {', '.join(missing_cols)}. "
                f"Use CBD(age_col, year_col, actual_col, expose_col) "
                f"to specify column names."
            )

        # grouping the data
        logger.info("grouping data by age and year")
        cbd_df = (
            df.groupby([self.age_col, self.year_col], observed=True)[
                [self.actual_col, self.expose_col]
            ]
            .sum()
            .reset_index()
        )
        logger.info("calculating qx_raw rates")
        cbd_df["qx_raw"] = np.where(
            cbd_df[self.actual_col] == 0,
            0,
            cbd_df[self.actual_col] / cbd_df[self.expose_col],
        )
        logger.info(
            f"there were {len(cbd_df[cbd_df['qx_raw']>1])} rates "
            f"over 1 that were capped."
        )
        cbd_df["qx_raw"] = cbd_df["qx_raw"].clip(upper=1)
        self.cbd_df = cbd_df
        logger.info(f"cbd_df shape: {self.cbd_df.shape}")

        return self.cbd_df

    def fit(self, cbd_df):
        """
        Get the forecasted mortality rates.

        Parameters
        ----------
        cbd_df : pd.DataFrame
            A DataFrame containing crude mortality rates for a given population.

        Returns
        -------
        cbd_df : pd.DataFrame
            A DataFrame containing the forecasted mortality rates.
            - rows: year
            - columns: age

        """
        logger.info("creating CBD model with qx_raw rates...")
        crude_pivot = cbd_df.pivot(
            index=self.year_col, columns=self.age_col, values="qx_raw"
        )

        year_start = crude_pivot.index.min()
        year_end = crude_pivot.index.max()
        ages = crude_pivot.columns
        self.ages = ages
        age_start = int(ages.min())
        age_end = int(ages.max())
        age_mean = ages.to_series().mean()

        logger.info(f"age range: {age_start}, {age_end}")
        logger.info(f"average age: {age_mean}")
        logger.info(f"year range: {year_start}, {year_end}")

        # qx_logit is the mortality matrix
        logger.debug("calculating qx_logit")
        qx_logit = self._logit(crude_pivot)

        # k_t_1 is the age effect (average mortality rate by age)
        logger.debug("calculating k_t_1 = mean rate per year")
        k_t_1 = qx_logit.mean(axis=1)
        self.k_t_1 = k_t_1

        # k_t_2 is the slope component
        logger.debug(
            "calculating k_t_2 = e1 / e2 \n"
            "e1 = Σ((age - age_mean) * qx_logit) \n"
            "e2 = Σ((age - age_mean)^2)"
        )
        age_diff = ages - age_mean
        self.age_diff = age_diff
        e1 = (age_diff * qx_logit).sum(axis=1)
        e2 = (age_diff.values**2).sum()
        k_t_2 = e1 / e2
        self.k_t_2 = k_t_2

        # qx_logit
        logger.debug("calculating qx_logit_cbd = k_t_1 + (age - age_mean) * k_t_2")
        qx_logit_cbd = k_t_1.values[:, np.newaxis] + (
            age_diff.values * k_t_2.values[:, np.newaxis]
        )
        qx_logit_cbd = pd.DataFrame(
            qx_logit_cbd, index=qx_logit.index, columns=qx_logit.columns
        )

        # qx_cbd
        logger.debug("calculating qx_cbd = exp(qx_logit_cbd) / (1 + exp(qx_logit_cbd))")
        qx_cbd = np.exp(qx_logit_cbd) / (1 + np.exp(qx_logit_cbd))

        # adding predictions to cbd_df
        logger.info("adding qx_cbd to cbd_df")
        cbd_df = pd.merge(
            cbd_df,
            qx_cbd.reset_index().melt(
                id_vars=self.year_col, var_name=self.age_col, value_name="qx_cbd"
            ),
            on=[self.year_col, self.age_col],
            how="left",
        ).astype({self.age_col: "int32", self.year_col: "int32"})
        self.cbd_df = cbd_df

        return cbd_df

    def forecast(self, years):
        """
        Forecast the mortality rates using deterministic random walk.

        Parameters
        ----------
        years : int
            The amount of years to forecast CBD model

        Returns
        -------
        cbd_df : pd.DataFrame
            A DataFrame containing the forecasted CBD mortality rates.

        """
        # checks if models have data needed
        if self.cbd_df is None:
            raise ValueError(
                "model is not fitted use fit method please use fit() method"
            )

        # initialize the variables
        variance = 0
        year_cols = list(
            range(self.k_t_1.index[-1] + 1, self.k_t_1.index[-1] + years + 1)
        )

        logger.info("forecasting qx_cbd using deterministic random walk...")
        # average change in k_t_1 and k_t_2
        mu = [
            (self.k_t_1.iloc[-1] - self.k_t_1.iloc[0]) / len(self.k_t_1),
            (self.k_t_2.iloc[-1] - self.k_t_2.iloc[0]) / len(self.k_t_2),
        ]

        # random walk
        rng = np.random.default_rng()
        k_1_f = (
            self.k_t_1.iloc[-1]
            + mu[0] * np.arange(1, years + 1)
            + rng.normal(scale=variance, size=years)
        )
        k_1_f = pd.Series(data=k_1_f, index=year_cols)
        k_1_f.index.name = self.year_col
        k_2_f = (
            self.k_t_2.iloc[-1]
            + mu[1] * np.arange(1, years + 1)
            + rng.normal(scale=variance, size=years)
        )
        k_2_f = pd.Series(data=k_2_f, index=year_cols)
        k_2_f.index.name = self.year_col
        self.k_1_f = k_1_f
        self.k_2_f = k_2_f

        # qx_logit
        logger.debug("calculating qx_logit_cbd = k_t_1 + (age - age_mean) * k_t_2")
        qx_logit_cbd = k_1_f.values[:, np.newaxis] + (
            self.age_diff.values * k_2_f.values[:, np.newaxis]
        )
        qx_logit_cbd = pd.DataFrame(qx_logit_cbd, index=year_cols, columns=self.ages)

        # qx_cbd
        logger.debug("calculating qx_cbd = exp(qx_logit_cbd) / (1 + exp(qx_logit_cbd))")
        qx_cbd = np.exp(qx_logit_cbd) / (1 + np.exp(qx_logit_cbd))

        # dataframe with forecast
        cbdf_df = pd.DataFrame(
            qx_cbd,
            index=year_cols,
            columns=self.ages,
        )
        cbdf_df.index.name = self.year_col
        cbdf_df.reset_index().melt(
            id_vars=self.year_col, var_name=self.age_col, value_name="qx_cbd"
        )

        return cbdf_df

    def map(self, df, age_col=None, year_col=None):
        """
        Map the mortality rates from the CBD model.

        Parameters
        ----------
        df : pd.DataFrame
            A DataFrame containing the data to predict.
        age_col : str, optional
            The column name for the attained age
        year_col : str, optional
            The column name for the observation year

        Returns
        -------
        cbd_df : pd.DataFrame
            A DataFrame containing the predicted mortality rates.

        """
        if age_col is None:
            age_col = self.age_col
        if year_col is None:
            year_col = self.year_col
        cbd_df = self.cbd_df

        # checks if models have data needed
        if cbd_df is None:
            raise ValueError(
                "model is not fitted use fit method please use fit() method"
            )
        if year_col not in cbd_df.columns or age_col not in cbd_df.columns:
            raise ValueError(f"{age_col} and {year_col} are required")

        # map rates to df
        logger.info("mapping qx_cbd to df")
        cbd_df = cbd_df.rename(columns={self.age_col: age_col, self.year_col: year_col})
        cbd_df = pd.merge(
            df,
            cbd_df[[age_col, year_col, "qx_cbd"]],
            on=[age_col, year_col],
            how="left",
            suffixes=("_old", ""),
        )
        if "qx_cbd_old" in cbd_df.columns:
            cbd_df.drop(columns=["qx_cbd_old"], inplace=True)

        return cbd_df

    def _logit(self, a):
        """
        Logit function.

        Parameters
        ----------
        a : float
            The value

        Returns
        -------
        logit : float
            The logit value

        """
        return np.log(a / (1 - a))