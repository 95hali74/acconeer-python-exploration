from abc import ABCMeta, abstractmethod
from copy import copy
import numpy as np


class BaseSessionConfig(metaclass=ABCMeta):
    _sweep_rate = None
    _sensors = [1]

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            if not hasattr(self.__class__, k):
                raise KeyError("unknown setting: {}".format(k))
            setattr(self, k, v)

    def __setattr__(self, name, value):
        if hasattr(self, name):
            object.__setattr__(self, name, value)
        else:
            raise AttributeError("{} has no setting {}".format(self.__class__.__name__, name))

    def __str__(self):
        attrs = [a for a in dir(self) if not a.startswith("_") and a.islower()]
        vals = [getattr(self, a) for a in attrs]
        d = {a: ("-" if v is None else v) for a, v in zip(attrs, vals)}
        s = self.__class__.__name__
        s += "".join(["\n  {:.<25} {}".format(a+" ", v) for (a, v) in d.items()])
        return s

    @property
    def sweep_rate(self):
        return self._sweep_rate

    @sweep_rate.setter
    def sweep_rate(self, rate):
        if rate < 1:
            raise ValueError("sweep rate must be >= 1")
        self._sweep_rate = rate

    @property
    def sensor(self):
        return self._sensors

    @sensor.setter
    def sensor(self, arg):
        if isinstance(arg, int):
            arg = [arg]
        elif isinstance(arg, list) and all([isinstance(e, int) for e in arg]):
            arg = copy(arg)
        else:
            raise TypeError("given sensor(s) must be either an int or a list of ints")
        self._sensors = arg

    @property
    @abstractmethod
    def mode(self):
        pass


class BaseServiceConfig(BaseSessionConfig):
    _gain = None
    _range_start = None
    _range_length = None
    _experimental_stitching = None

    @property
    def gain(self):
        return self._gain

    @gain.setter
    def gain(self, gain):
        if not 0 <= gain <= 1:
            raise ValueError("gain must be between 0 and 1")
        self._gain = gain

    @property
    def range_start(self):
        return self._range_start

    @range_start.setter
    def range_start(self, start):
        if getattr(self, "session_profile", None) != EnvelopeServiceConfig.DIRECT_LEAKAGE:
            if start < 0:
                raise ValueError("range start must be positive")
        self._range_start = start

    @property
    def range_length(self):
        return self._range_length

    @range_length.setter
    def range_length(self, length):
        if length < 0:
            raise ValueError("range length must be positive")
        self._range_length = length

    @property
    def range_interval(self):
        if None in [self._range_start, self._range_length]:
            return None
        return np.array([self.range_start, self.range_end])

    @range_interval.setter
    def range_interval(self, interval):
        start, end = interval
        self.range_start = start
        self.range_length = end - start

    @property
    def range_end(self):
        if None in [self._range_start, self._range_length]:
            return None
        return self._range_start + self._range_length

    @range_end.setter
    def range_end(self, range_end):
        self.range_length = range_end - self.range_start

    @property
    def experimental_stitching(self):
        return self._experimental_stitching

    @experimental_stitching.setter
    def experimental_stitching(self, experimental_stitching):
        self._experimental_stitching = experimental_stitching


class BaseDenseServiceConfig(BaseServiceConfig):
    _running_average_factor = None

    @property
    def running_average_factor(self):
        return self._running_average_factor

    @running_average_factor.setter
    def running_average_factor(self, factor):
        if not (0 < factor < 1):
            raise ValueError("running average factor must be between 0 and 1")
        self._running_average_factor = factor


class PowerBinServiceConfig(BaseServiceConfig):
    _bin_count = None

    @property
    def mode(self):
        return "power_bin"

    @property
    def bin_count(self):
        return self._bin_count

    @bin_count.setter
    def bin_count(self, count):
        if count <= 0:
            raise ValueError("bin count must be > 0")
        self._bin_count = count


class EnvelopeServiceConfig(BaseDenseServiceConfig):
    MAX_DEPTH_RESOLUTION = 0
    MAX_SNR = 1
    DIRECT_LEAKAGE = 2
    PROFILES = [MAX_DEPTH_RESOLUTION, MAX_SNR, DIRECT_LEAKAGE]

    _session_profile = MAX_SNR
    _compensate_phase = None

    @property
    def mode(self):
        return "envelope"

    @property
    def compensate_phase(self):
        return self._compensate_phase

    @compensate_phase.setter
    def compensate_phase(self, enabled):
        self._compensate_phase = enabled

    @property
    def session_profile(self):
        return self._session_profile

    @session_profile.setter
    def session_profile(self, profile):
        if profile not in self.PROFILES:
            raise ValueError("invalid profile")
        self._session_profile = profile


class IQServiceConfig(BaseDenseServiceConfig):
    @property
    def mode(self):
        return "iq"


class SparseServiceConfig(BaseServiceConfig):
    _number_of_subsweeps = 16

    @property
    def mode(self):
        return "sparse"

    @property
    def number_of_subsweeps(self):
        return self._number_of_subsweeps

    @number_of_subsweeps.setter
    def number_of_subsweeps(self, number_of_subsweeps):
        if number_of_subsweeps < 1:
            raise ValueError("number of subsweeps must be > 0")
        if number_of_subsweeps > 16:
            raise ValueError("number of subsweeps must be <= 16")
        self._number_of_subsweeps = number_of_subsweeps


class DistancePeakDetectorConfig(BaseServiceConfig):
    @property
    def mode(self):
        return "distance_peak_fix_threshold"
