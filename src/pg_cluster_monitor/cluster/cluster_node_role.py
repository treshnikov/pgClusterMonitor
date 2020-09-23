import enum


class DbRole(enum.Enum):
    UNKNOWN = 0
    MASTER = 1
    STANDBY = 2

    def __str__(self):
        if self.value == 0:
            return "UNKNOWN"

        if self.value == 1:
            return "MASTER"

        if self.value == 2:
            return "STANDBY"

    def __repr__(self):
        return self.__str__()
