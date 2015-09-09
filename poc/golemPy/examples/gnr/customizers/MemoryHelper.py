import logging

logger = logging.getLogger(__name__)

options = {
    0: 'kB',
    1: 'MB',
    2: 'GB'
}

def dirSizeToDisplay(dirSize):
    if dirSize / (1024 * 1024 * 1024) > 0:
        dirSize = round(float(dirSize) / (1024 * 1024 * 1024), 1)
        index = 2
    elif dirSize / (1024 * 1024) > 0:
        dirSize = round(float(dirSize) / (1024 * 1024), 1)
        index = 1
    else:
        dirSize = round(float(dirSize) / 1024, 1)
        index = 0
    return dirSize, index

def resource_sizeToDisplay(max_resource_size):
    if max_resource_size / (1024 * 1024) > 0:
        max_resource_size /= (1024 * 1024)
        index = 2
    elif max_resource_size / 1024 > 0:
        max_resource_size /= 1024
        index = 1
    else:
        index = 0
    return max_resource_size, index

def translateResourceIndex(index):
    if index in options:
        return options[ index ]
    else:
        logger.error("Wrong memory unit index: {} ".format(index))
        return ''