
import logging

log = logging.getLogger("systogony")


class NoSuchEnvironmentError(Exception):
    """

    """

class BlueprintLoaderError(Exception):
    """

    """
    def __init__(self, msg):
        log.error(msg)
        super().__init__(msg)

class NonMatchingPathSignal(Exception):
    """

    """

class MissingServiceError(Exception):
    """

    """

class NotReadySignal(Exception):
    """

    """
