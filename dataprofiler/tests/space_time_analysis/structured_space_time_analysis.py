"""Contains space and time analysis tests for the Dataprofiler"""
import json
import os
import random
import time
from collections import defaultdict
from typing import Dict, List, Optional

import memray
import numpy as np
import pandas as pd
import tensorflow as tf
from numpy.random import Generator

try:
    import sys

    sys.path.insert(0, "../../..")
    import dataprofiler as dp
except ImportError:
    import dataprofiler as dp

from dataset_generation import generate_dataset_by_class, nan_injection

from dataprofiler import StructuredProfiler

# suppress TF warnings
tf.compat.v1.logging.set_verbosity(tf.compat.v1.logging.ERROR)


def dp_profile_space_analysis(
    data: pd.DataFrame,
    path: str,
    options: Optional[Dict] = None,
) -> StructuredProfiler:
    """
    Generate memray bin file of the space analysis of dp.Profiler function

    :param data: DataFrame that is to be profiled
    :type data: pandas.DataFrame
    :param path: Path to output the memray bin file generated for space analysis
    :type path: string
    :param options: options for the dataprofiler intialization
    :type options: Dict, None, optional

    :return: The StructuredProfile generated by dp.Profiler
    """
    with memray.Tracker(path):
        profile = dp.Profiler(data, options=options, samples_per_update=len(data))

    return profile


def dp_merge_space_analysis(profile: StructuredProfiler, path: str):
    """
    Generate memray bin file of the space analysis of merge profile functionality

    :param profile: Profile that is to be merged with itself
    :type profile: StructuredProfile
    :param path: Path to output the memray bin file generated for space analysis
    :type path: string
    """

    with memray.Tracker(path):
        _ = profile + profile


def dp_space_time_analysis(
    rng: Generator,
    sample_sizes: List,
    data: pd.DataFrame,
    path: str = "./time_analysis/structured_profiler_times.json",
    percent_to_nan: float = 0.0,
    allow_subsampling: bool = True,
    options: Optional[Dict] = None,
    space_analysis=True,
    time_analysis=True,
):
    """
    Run time analysis for profile and merge functionality

    :param rng: the np rng object used to generate random values
    :type rng: numpy Generator
    :param sample_sizes: List of sample sizes of dataset to be analyzed
    :type sample_sizes: list
    :param data: DataFrame to be used for time analysis
    :type data: pandas DataFrame
    :param path: Path to output json file with all time analysis info
    :type path: string, optional
    :param percent_to_nan: Percentage of dataset that needs to be nan values
    :type percent_to_nan: float, optional
    :param allow_subsampling: boolean to allow subsampling when running analysis
    :type allow_subsampling: bool, optional
    :param options: options for the dataprofiler intialization
    :type options: Dict, None, optional
    :param options: options for the dataprofiler intialization
    :type options: Dict, None, optional
    :param space_analysis: boolean to turn on or off the space analysis functionality
    :type space_analysis: bool, optional
    :param time_analysis: boolean to turn on or off the time analysis functionality
    :type time_analysis: bool, optional
    """
    # [0] allows model to be initialized and added to labeler
    sample_sizes = [0] + sample_sizes
    profile_times = []
    for sample_size in sample_sizes:
        # setup time dict

        print(f"Evaluating sample size: {sample_size}")
        replace = False
        if sample_size > len(data):
            replace = True

        sample_data = (
            data.sample(sample_size, replace=replace)
            .sort_index()
            .reset_index(drop=True)
        )

        if percent_to_nan:
            sample_data = nan_injection(rng, sample_data)
        if time_analysis:
            # time profiling
            start_time = time.time()
            if allow_subsampling:
                profiler = dp.Profiler(sample_data, options=options)
            else:
                print(f"Length of dataset {len(sample_data)}")
                profiler = dp.Profiler(
                    sample_data, samples_per_update=len(sample_data), options=options
                )
            total_time = time.time() - start_time

            # get overall time for merging profiles
            start_time = time.time()
            try:
                merged_profile = profiler + profiler
            except ValueError:
                pass  # empty profile merge if 0 data
            merge_time = time.time() - start_time

            # get times for each profile in the columns
            for profile in profiler.profile:
                compiler_times = defaultdict(list)

                for compiler_name in profile.profiles:
                    compiler = profile.profiles[compiler_name]
                    inspector_times = dict()
                    for inspector_name in compiler._profiles:
                        inspector = compiler._profiles[inspector_name]
                        inspector_times[inspector_name] = inspector.times
                    compiler_times[compiler_name] = inspector_times
                column_profile_time = {
                    "name": profile.name,
                    "sample_size": sample_size,
                    "total_time": total_time,
                    "column": compiler_times,
                    "merge": merge_time,
                    "percent_to_nan": percent_to_nan,
                    "allow_subsampling": allow_subsampling,
                    "is_data_labeler": options.structured_options.data_labeler.is_enabled,
                    "is_multiprocessing": options.structured_options.multiprocess.is_enabled,
                }
                profile_times += [column_profile_time]

            # add time for for Top-level
            if sample_size:
                profile_times += [
                    {
                        "name": "StructuredProfiler",
                        "sample_size": sample_size,
                        "total_time": total_time,
                        "column": profiler.times,
                        "merge": merge_time,
                        "percent_to_nan": percent_to_nan,
                        "allow_subsampling": allow_subsampling,
                        "is_data_labeler": options.structured_options.data_labeler.is_enabled,
                        "is_multiprocessing": options.structured_options.multiprocess.is_enabled,
                    }
                ]
            time_report_path = os.path.join(
                os.path.dirname(path), f"time_report_{sample_size}.txt"
            )
            if not os.path.exists(os.path.dirname(time_report_path)):
                os.makedirs(os.path.dirname(time_report_path))

            with open(time_report_path, "a") as f:
                f.write(f"COMPLETE sample size: {sample_size} \n")
                print(f"COMPLETE sample size: {sample_size}")
                f.write(f"Profiled in {total_time} seconds \n")
                print(f"Profiled in {total_time} seconds")
                f.write(f"Merge in {merge_time} seconds \n")
                print(f"Merge in {merge_time} seconds")
                print()
                f.close()

        if space_analysis:
            if not os.path.exists("./space_analysis/"):
                os.makedirs("./space_analysis/")
            profile = dp_profile_space_analysis(
                data=sample_data,
                path=f"./space_analysis/profile_space_analysis_{sample_size}.bin",
                options=options,
            )
            print(
                f"Profile Space Analysis results saved to "
                f"./space_analysis/profile_space_analysis_{sample_size}.bin"
            )
            try:
                dp_merge_space_analysis(
                    profile=profile,
                    path=f"./space_analysis/merge_space_analysis_{sample_size}.bin",
                )
                print(
                    f"Profile Space Analysis results saved to "
                    f"./space_analysis/profile_space_analysis_{sample_size}.bin"
                )
            except ValueError:
                # empty profile merge if 0 data
                print(
                    f"Warning: Profile merge failure on dataset set size {sample_size}"
                )
                os.remove(f"./space_analysis/profile_space_analysis_{sample_size}.bin")

    # Print dictionary with profile times
    print("Results Saved")
    # print(json.dumps(profile_times, indent=4))

    # only works if columns all have unique names
    times_table = (
        pd.json_normalize(profile_times).set_index(["name", "sample_size"]).sort_index()
    )

    # save json and times table
    if time_analysis:
        if not os.path.exists(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))
        with open(path, "w") as fp:
            json.dump(profile_times, fp, indent=4)
        times_table.to_csv(path)


if __name__ == "__main__":
    ################################################################################
    ######################## set any optional changes here #########################
    ################################################################################
    OPTIONS = dp.ProfilerOptions()

    # these two options default to True if commented out
    OPTIONS.structured_options.multiprocess.is_enabled = False
    OPTIONS.structured_options.data_labeler.is_enabled = False

    # parameter alteration
    ALLOW_SUBSAMPLING = False  # profiler to subsample the dataset if large
    PERCENT_TO_NAN = 0.0  # Value must be between 0 and 100

    # If set to None new dataset is generated.
    DATASET_PATH = None

    TIME_ANALYSIS = True
    SPACE_ANALYSIS = True
    SAMPLE_SIZES = [100, 1000, 5000, 7500, int(1e5)]

    # set seed
    RANDOM_SEED = 0
    ################################################################################

    random.seed(RANDOM_SEED)
    np.random.seed(RANDOM_SEED)
    dp.set_seed(RANDOM_SEED)
    _rng = np.random.default_rng(seed=RANDOM_SEED)

    # Generate and load data
    if not DATASET_PATH:
        _full_dataset = generate_dataset_by_class(
            _rng,
            dataset_length=max(SAMPLE_SIZES),
            path="./data/all_data_class_100000.csv",
        )
        print(f"Dataset of size {max(SAMPLE_SIZES)} created.")
    else:
        full_dataset = dp.Data(DATASET_PATH)

    dp_space_time_analysis(
        _rng,
        SAMPLE_SIZES,
        _full_dataset,
        path="./time_analysis/structured_profiler_times.json",
        percent_to_nan=PERCENT_TO_NAN,
        options=OPTIONS,
        allow_subsampling=ALLOW_SUBSAMPLING,
        time_analysis=TIME_ANALYSIS,
        space_analysis=SPACE_ANALYSIS,
    )
