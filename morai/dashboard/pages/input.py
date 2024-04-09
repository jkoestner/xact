"""Data Input dashboard."""

import json

import dash_bootstrap_components as dbc
import dash_extensions.enrich as dash
from dash_extensions.enrich import (
    Input,
    Output,
    State,
    callback,
    dcc,
    html,
)

from morai.dashboard.utils import dashboard_helper as dh
from morai.utils import custom_logger, helpers

logger = custom_logger.setup_logging(__name__)

dash.register_page(__name__, path="/input", title="morai - Input")


#   _                            _
#  | |    __ _ _   _  ___  _   _| |_
#  | |   / _` | | | |/ _ \| | | | __|
#  | |__| (_| | |_| | (_) | |_| | |_
#  |_____\__,_|\__, |\___/ \__,_|\__|
#              |___/


def layout():
    """Input layout."""
    return html.Div(
        [
            dbc.Row(
                html.H4(
                    "Data Input",
                    className="bg-primary text-white p-2 mb-2 text-center",
                )
            ),
            dbc.Row(
                html.P(
                    [
                        "This page is used to load the configuration file "
                        "and display the configuration.",
                        html.Br(),
                        "The configuration file should be located in: ",
                        html.Span(
                            f"{helpers.FILES_PATH!s}",
                            style={"fontWeight": "bold"},
                        ),
                        html.Br(),
                        "The name should be: ",
                        html.Span(
                            "dashboard_config.yaml", style={"fontWeight": "bold"}
                        ),
                    ],
                ),
            ),
            dbc.Container(
                [
                    dbc.Row(
                        html.Div(
                            html.H5(
                                "Select File",
                                style={
                                    "border-bottom": "1px solid black",
                                    "padding-bottom": "5px",
                                },
                            ),
                            style={
                                "width": "fit-content",
                                "padding": "0px",
                            },
                        ),
                    ),
                    dbc.Row(
                        [
                            dbc.Col(
                                dcc.Dropdown(
                                    id="dataset-dropdown",
                                    options=[
                                        {"label": key, "value": key}
                                        for key in list(
                                            dh.load_config()["datasets"].keys()
                                        )
                                    ],
                                    placeholder="Select a dataset",
                                ),
                                width=3,
                            ),
                            dbc.Col(
                                dbc.Button(
                                    "Load Config",
                                    id="load-button",
                                    className="btn btn-primary",
                                ),
                                width=1,
                            ),
                        ],
                    ),
                ],
                className="m-1 bg-light border",
            ),
            dbc.Row(
                [
                    html.Div(
                        html.H5(
                            "Configuration",
                            style={
                                "border-bottom": "1px solid black",
                                "padding-bottom": "5px",
                            },
                        ),
                        style={
                            "width": "fit-content",
                            "padding": "0px",
                        },
                    ),
                    html.H6(
                        "General Config",
                    ),
                    dbc.Col(
                        dcc.Markdown(id="general-config-str"),
                        width=12,
                    ),
                    html.H6(
                        "Dataset Config",
                    ),
                    dbc.Col(
                        dcc.Markdown(id="dataset-config-str"),
                        width=12,
                    ),
                ],
                className="m-1 bg-light border",
            ),
        ],
        className="container",
    )


#    ____      _ _ _                _
#   / ___|__ _| | | |__   __ _  ___| | _____
#  | |   / _` | | | '_ \ / _` |/ __| |/ / __|
#  | |__| (_| | | | |_) | (_| | (__|   <\__ \
#   \____\__,_|_|_|_.__/ \__,_|\___|_|\_\___/
@callback(
    Output("store-config", "data"),
    [Input("load-button", "n_clicks")],
    [State("dataset-dropdown", "value")],
    prevent_initial_call=True,
)
def load_config(n_clicks, dataset):
    """Load the configuration file."""
    logger.debug("load config")
    if n_clicks:
        config = dh.load_config()
        config["general"]["dataset"] = dataset
        dh.write_config(config)

        return config


@callback(
    [
        Output("general-config-str", "children"),
        Output("dataset-config-str", "children"),
    ],
    [Input("store-config", "data")],
    # prevent_initial_call=True,
)
def display_general_config(config_data):
    """Display the configuration file."""
    if config_data is None:
        return dash.no_update, dash.no_update
    logger.debug("display config")
    general_dict = config_data["general"]
    general_json = json.dumps(general_dict, indent=2)
    general_config_str = f"```json\n{general_json}\n```"
    dataset_dict = config_data["datasets"][general_dict["dataset"]]
    dataset_json = json.dumps(dataset_dict, indent=2)
    dataset_config_str = f"```json\n{dataset_json}\n```"
    return general_config_str, dataset_config_str
