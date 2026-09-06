"""Single source of truth for the CS2 map configuration (audit A-3).

Previously this dict was duplicated (and drifting in formatting) between
the inference entry (demo_analysis/get_round_win_rate.py) and the training
data builder (data/create_training_data_wds_space_only.py). Both import it
from here now. Note: the model map set intentionally covers the 8 maps the
v3 checkpoints were trained on; de_vertigo/de_ancient_night demos are not
supported by the current models.
"""

MAP_CONFIG = {
    "maps": {
        "de_mirage": {
            "center": [-605.8900146484375, -866.8900146484375, -171.6199951171875],
        },
        "de_dust2": {
            "center": [-199.0, 977.0, 32.220001220703125],
        },
        "de_inferno": {
            "center": [481.07000732421875, 1396.47998046875, 137.91000366210938],
        },
        "de_nuke": {
            "center": [265.9599914550781, -772.5, -381.8999938964844],
        },
        "de_overpass": {
            "center": [-2027.3900146484375, -812.9000244140625, 324.95001220703125],
        },
        "de_ancient": {
            "center": [-435.5, -348.0, 43.650001525878906],
        },
        "de_anubis": {
            "center": [-77.38999938964844, 618.9000244140625, -6.800000190734863],
        },
        "de_train": {
            "center": [-118.25, -2.0, -128.52000427246094],
        },
    },
    "ranges": {
        "x": [-5000, 5000],
        "y": [-5000, 5000],
        "z": [-2000, 2000],
    },
}

MAP_NAME_TO_IDX = {map_name: idx for idx, map_name in enumerate(MAP_CONFIG["maps"].keys())}
