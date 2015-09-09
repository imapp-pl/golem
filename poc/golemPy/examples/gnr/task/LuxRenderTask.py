import logging
import random
import os
import tempfile

from collections import OrderedDict
from PIL import Image, ImageChops

from golem.core.simpleexccmd import exec_cmd
from golem.task.TaskState import SubtaskStatus
from golem.environments.Environment import Environment

from  examples.gnr.RenderingTaskState import RendererDefaults, RendererInfo
from examples.gnr.RenderingEnvironment import LuxRenderEnvironment
from examples.gnr.RenderingDirManager import getTestTaskPath
from examples.gnr.task.ImgRepr import loadImg, blend
from  examples.gnr.task.GNRTask import GNROptions, checkSubtask_idWrapper
from  examples.gnr.task.RenderingTask import RenderingTask, RenderingTaskBuilder
from examples.gnr.task.SceneFileEditor import regenerateLuxFile
from examples.gnr.ui.LuxRenderDialog import LuxRenderDialog
from examples.gnr.customizers.LuxRenderDialogCustomizer import LuxRenderDialogCustomizer

logger = logging.getLogger(__name__)

##############################################
def buildLuxRenderInfo():
    defaults = RendererDefaults()
    defaults.outputFormat = "EXR"
    defaults.mainProgramFile = os.path.normpath(os.path.join(os.environ.get('GOLEM'), 'examples/tasks/luxTask.py'))
    defaults.minSubtasks = 1
    defaults.maxSubtasks = 100
    defaults.defaultSubtasks = 5

    renderer = RendererInfo("LuxRender", defaults, LuxRenderTaskBuilder, LuxRenderDialog, LuxRenderDialogCustomizer, LuxRenderOptions)
    renderer.outputFormats = ["EXR", "PNG", "TGA"]
    renderer.sceneFileExt = [ "lxs" ]
    renderer.get_taskNumFromPixels = get_taskNumFromPixels
    renderer.get_taskBoarder = get_taskBoarder

    return renderer

def get_taskBoarder(startTask, endTask, totalTasks, resX = 300 , resY = 200, numSubtasks = 20):
    boarder = []
    for i in range(0, resY):
        boarder.append((0, i))
        boarder.append((resX - 1, i))
    for i in range(0, resX):
        boarder.append((i, 0))
        boarder.append((i, resY - 1))
    return boarder

def get_taskNumFromPixels(pX, pY, totalTasks, resX = 300, resY = 200):
    return 1

##############################################
class LuxRenderOptions(GNROptions):

    #######################
    def __init__(self):
        self.environment = LuxRenderEnvironment()
        self.halttime = 600
        self.haltspp = 1
        self.sendBinaries = False
        self.luxconsole = self.environment.getLuxConsole()

    #######################
    def addToResources(self, resources):
        if self.sendBinaries and os.path.isfile(self.luxconsole):
            resources.add(os.path.normpath(self.luxconsole))
        return resources

    #######################
    def removeFromResources(self, resources):
        if self.sendBinaries and os.path.normpath(self.luxconsole) in resources:
            resources.remove(os.path.normpath(self.luxconsole))
        return resources

##############################################
class LuxRenderTaskBuilder(RenderingTaskBuilder):
    #######################
    def build(self):
        mainSceneDir = os.path.dirname(self.taskDefinition.mainSceneFile)

        luxTask = LuxTask( self.client_id,
                            self.taskDefinition.task_id,
                            mainSceneDir,
                            self.taskDefinition.mainSceneFile,
                            self.taskDefinition.mainProgramFile,
                            self._calculateTotal(buildLuxRenderInfo(), self.taskDefinition),
                            self.taskDefinition.resolution[0],
                            self.taskDefinition.resolution[1],
                            os.path.splitext(os.path.basename(self.taskDefinition.output_file))[0],
                            self.taskDefinition.output_file,
                            self.taskDefinition.outputFormat,
                            self.taskDefinition.full_task_timeout,
                            self.taskDefinition.subtask_timeout,
                            self.taskDefinition.resources,
                            self.taskDefinition.estimated_memory,
                            self.root_path,
                            self.taskDefinition.rendererOptions.halttime,
                            self.taskDefinition.rendererOptions.haltspp,
                            self.taskDefinition.rendererOptions.sendBinaries,
                            self.taskDefinition.rendererOptions.luxconsole
       )

        return self._setVerificationOptions(luxTask)

##############################################
class LuxTask(RenderingTask):
    #######################
    def __init__(  self,
                    client_id,
                    task_id,
                    mainSceneDir,
                    mainSceneFile,
                    mainProgramFile,
                    totalTasks,
                    resX,
                    resY,
                    outfilebasename,
                    output_file,
                    outputFormat,
                    full_task_timeout,
                    subtask_timeout,
                    taskResources,
                    estimated_memory,
                    root_path,
                    halttime,
                    haltspp,
                    ownBinaries,
                    luxconsole,
                    return_address = "",
                    return_port = 0,
                    key_id = ""):

        RenderingTask.__init__(self, client_id, task_id, return_address, return_port, key_id,
                                 LuxRenderEnvironment.get_id(), full_task_timeout, subtask_timeout,
                                 mainProgramFile, taskResources, mainSceneDir, mainSceneFile,
                                 totalTasks, resX, resY, outfilebasename, output_file, outputFormat,
                                 root_path, estimated_memory)

        self.halttime = halttime
        self.haltspp = haltspp
        self.ownBinaries = ownBinaries
        self.luxconsole = luxconsole

        try:
            with open(mainSceneFile) as f:
                self.sceneFileSrc = f.read()
        except Exception, err:
            logger.error("Wrong scene file: {}".format(str(err)))
            self.sceneFileSrc = ""

        self.output_file, _ = os.path.splitext(self.output_file)
        self.numAdd = 0

        self.previewEXR = None
        if self.ownBinaries:
            self.header.environment = Environment.get_id()

    #######################
    def query_extra_data(self, perf_index, num_cores = 0, client_id = None):
        if not self._acceptClient(client_id):
            logger.warning(" Client {} banned from this task ".format(client_id))
            return None

        startTask, endTask = self._getNextTask()
        if startTask is None or endTask is None:
            logger.error("Task already computed")
            return None

        working_directory = self._getWorkingDirectory()
        minX = 0
        maxX = 1
        minY = (startTask - 1) * (1.0 / float(self.totalTasks))
        maxY = (endTask) * (1.0 / float(self.totalTasks))

        if self.halttime > 0:
            writeInterval =  int(self.halttime / 2)
        else:
            writeInterval = 60
        sceneSrc = regenerateLuxFile(self.sceneFileSrc, self.resX, self.resY, self.halttime, self.haltspp, writeInterval, [0, 1, 0, 1], "PNG")
        sceneDir= os.path.dirname(self._getSceneFileRelPath())

        if self.ownBinaries:
            luxConsole = self._getLuxConsoleRelPath()
        else:
            luxConsole = 'luxconsole.exe'

        numThreads = max(num_cores, 1)

        extra_data =          {      "pathRoot" : self.mainSceneDir,
                                    "startTask" : startTask,
                                    "endTask" : endTask,
                                    "totalTasks" : self.totalTasks,
                                    "outfilebasename" : self.outfilebasename,
                                    "sceneFileSrc" : sceneSrc,
                                    "sceneDir": sceneDir,
                                    "numThreads": numThreads,
                                    "ownBinaries": self.ownBinaries,
                                    "luxConsole": luxConsole
                                }

        hash = "{}".format(random.getrandbits(128))
        self.subTasksGiven[ hash ] = extra_data
        self.subTasksGiven[ hash ][ 'status' ] = SubtaskStatus.starting
        self.subTasksGiven[ hash ][ 'perf' ] = perf_index
        self.subTasksGiven[ hash ][ 'client_id' ] = client_id

        return self._newComputeTaskDef(hash, extra_data, working_directory, perf_index)


    #######################
    def query_extra_dataForTestTask(self):
        self.test_taskResPath = getTestTaskPath(self.root_path)
        logger.debug(self.test_taskResPath)
        if not os.path.exists(self.test_taskResPath):
            os.makedirs(self.test_taskResPath)

        sceneSrc = regenerateLuxFile(self.sceneFileSrc, 1, 1, 5, 0, 1, [0, 1, 0, 1 ], "PNG")
        working_directory = self._getWorkingDirectory()
        sceneDir= os.path.dirname(self._getSceneFileRelPath())

        if self.ownBinaries:
            luxConsole = self._getLuxConsoleRelPath()
        else:
            luxConsole = 'luxconsole.exe'

        extra_data = {
            "pathRoot" : self.mainSceneDir,
            "startTask": 1,
            "endTask": 1,
            "totalTasks": 1,
            "outfilebasename": self.outfilebasename,
            "sceneFileSrc": sceneSrc,
            "sceneDir": sceneDir,
            "numThreads": 1,
            "ownBinaries": self.ownBinaries,
            "luxConsole": luxConsole
        }

        hash = "{}".format(random.getrandbits(128))


        return self._newComputeTaskDef(hash, extra_data, working_directory, 0)

    #######################
    def _short_extra_data_repr(self, perf_index, extra_data):
        l = extra_data
        return "startTask: {}, outfilebasename: {}, sceneFileSrc: {}".format(l['startTask'], l['outfilebasename'], l['sceneFileSrc'])

    #######################
    def computation_finished(self, subtask_id, task_result, dir_manager = None, result_type = 0):
        tmpDir = dir_manager.get_task_temporary_dir(self.header.task_id, create = False)
        self.tmpDir = tmpDir

        trFiles = self.loadTaskResults(task_result, result_type, tmpDir)

        if len(task_result) > 0:
            numStart = self.subTasksGiven[ subtask_id ][ 'startTask' ]
            self.subTasksGiven[ subtask_id ][ 'status' ] = SubtaskStatus.finished
            for trFile in trFiles:
                _, ext = os.path.splitext(trFile)
                if ext == '.flm':
                    self.collectedFileNames[ numStart ] = trFile
                    self.numTasksReceived += 1
                    self.countingNodes[ self.subTasksGiven[ subtask_id ][ 'client_id' ] ] = 1
                else:
                    self.subTasksGiven[ subtask_id ][ 'previewFile' ] = trFile
                    self._updatePreview(trFile, numStart)
        else:
            self._markSubtaskFailed(subtask_id)

        if self.numTasksReceived == self.totalTasks:
            self.__generateFinalFLM()
            self.__generateFinalFile()

    #######################
    def __generateFinalFLM(self):
        output_file_name = u"{}".format(self.output_file, self.outputFormat)
        self.collectedFileNames = OrderedDict(sorted(self.collectedFileNames.items()))
        files = " ".join(self.collectedFileNames.values())
        env = LuxRenderEnvironment()
        luxMerger = env.getLuxMerger()
        if luxMerger is not None:
            cmd = "{} -o {}.flm {}".format(luxMerger, self.output_file, files)

            logger.debug("Lux Merger cmd: {}".format(cmd))
            exec_cmd(cmd)

    #######################
    def __generateFinalFile(self):

        if self.halttime > 0:
            writeInterval =  int(self.halttime / 2)
        else:
            writeInterval = 60

        sceneSrc = regenerateLuxFile(self.sceneFileSrc, self.resX, self.resY, self.halttime, self.haltspp, writeInterval, [0, 1, 0, 1], self.outputFormat)

        tmpSceneFile = self.__writeTmpSceneFile(sceneSrc)
        self.__formatLuxRenderCmd(tmpSceneFile)

    #######################
    def __writeTmpSceneFile(self, sceneFileSrc):
        tmpSceneFile = tempfile.TemporaryFile(suffix = ".lxs", dir = os.path.dirname(self.mainSceneFile))
        tmpSceneFile.close()
        with open(tmpSceneFile.name, 'w') as f:
            f.write(sceneFileSrc)
        return tmpSceneFile.name

    #######################
    def __formatLuxRenderCmd(self, sceneFile):
        cmdFile = LuxRenderEnvironment().getLuxConsole()
        outputFLM = "{}.flm".format(self.output_file)
        cmd = '"{}" "{}" -R "{}" -o "{}" '.format(cmdFile, sceneFile, outputFLM, self.output_file)
        logger.debug("Last flm cmd {}".format(cmd))
        prevPath = os.getcwd()
        os.chdir(os.path.dirname(self.mainSceneFile))
        exec_cmd(cmd)
        os.chdir(prevPath)

    #######################
    def _updatePreview(self, newChunkFilePath, chunkNum):
        self.numAdd += 1
        if newChunkFilePath.endswith(".exr"):
            self.__updatePreviewFromEXR(newChunkFilePath)
        else:
            self.__updatePreviewFromPILFile(newChunkFilePath)

    #######################
    def __updatePreviewFromPILFile(self, newChunkFilePath):
        img = Image.open(newChunkFilePath)

        imgCurrent = self._openPreview()
        imgCurrent = ImageChops.blend(imgCurrent, img, 1.0 / float(self.numAdd))
        imgCurrent.save(self.previewFilePath, "BMP")

    #######################
    def __updatePreviewFromEXR(self, newChunkFile):
        if self.previewEXR is None:
            self.previewEXR = loadImg(newChunkFile)
        else:
            self.previewEXR = blend(self.previewEXR, loadImg(newChunkFile), 1.0 / float(self.numAdd))

        imgCurrent = self._openPreview()
        img = self.previewEXR.toPIL()
        img.save(self.previewFilePath, "BMP")

    #######################
    @checkSubtask_idWrapper
    def _removeFromPreview(self, subtask_id):
        previewFiles = []
        for subId, task in self.subTasksGiven.iteritems():
            if subId != subtask_id and task['status'] == 'Finished' and 'previewFile' in task:
                previewFiles.append(task['previewFile'])

        self.previewFilePath = None
        self.numAdd = 0
        for f in previewFiles:
            self._updatePreview(f, None)

    #######################
    def _getLuxConsoleRelPath(self):
        luxconsoleRel = os.path.relpath(os.path.dirname(self.luxconsole), os.path.dirname(self.mainSceneFile))
        luxconsoleRel = os.path.join(luxconsoleRel, os.path.basename(self.luxconsole))
        return luxconsoleRel
