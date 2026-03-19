# Common Exceptions Module
from common.exceptions.vehicle_exceptions import (
    VehicleException,
    VehicleConnectionError,
    VehicleStateError,
    VehicleConfigError
)
from common.exceptions.network_exceptions import (
    NetworkException,
    CANBusError,
    ADBConnectionError,
    SOMEIPError,
    DoIPError,
    MQTTError
)
from common.exceptions.test_exceptions import (
    TestException,
    TestPreconditionError,
    TestTimeoutError,
    TestDataError,
    TestEnvironmentError
)
from common.exceptions.hardware_exceptions import (
    HardwareException,
    HILConnectionError,
    PowerSupplyError,
    MeasurementError
)

__all__ = [
    "VehicleException",
    "VehicleConnectionError",
    "VehicleStateError",
    "VehicleConfigError",
    "NetworkException",
    "CANBusError",
    "ADBConnectionError",
    "SOMEIPError",
    "DoIPError",
    "MQTTError",
    "TestException",
    "TestPreconditionError",
    "TestTimeoutError",
    "TestDataError",
    "TestEnvironmentError",
    "HardwareException",
    "HILConnectionError",
    "PowerSupplyError",
    "MeasurementError",
]