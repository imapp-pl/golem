class NodesManagerLogicTest:

    ########################
    def __init__( self, simulator ):
        self.simulator = simulator

    ########################
    def runAdditionalNodes( self, numNodes ):
        for i in range( numNodes ):
            self.simulator.addNewNode()

    ########################
    def terminateNode( self, uid ):
        self.simulator.terminateNode( uid )

    ########################
    def terminateAllNodes( self ):
        self.simulator.terminateAllNodes()

    ########################
    def enqueueNewTask( self, uid, w, h, numSamplesPerPixel, fileName ):
        self.simulator.enqueueNodeTask( uid, w, h, numSamplesPerPixel, fileName )


import subprocess
from managerserver import ManagerServer
import time
import random
from taskbase import TaskHeader
from exampletasks import VRayTracingTask

class EmptyManagerLogic:

    ########################
    def __init__( self, port, managerServer ):
        self.reactor = None
        self.managerServer = managerServer
        self.activeNodes = []

    ########################
    def setReactor( self, reactor ):
        self.reactor = reactor
        self.managerServer.setReactor( reactor )

    ########################
    def getReactor( self ):
        return self.reactor

    ########################
    def runAdditionalNodes( self, numNodes ):
        for i in range( numNodes ):
            time.sleep( 0.1 )
            pc = subprocess.Popen( ["python", "clientmain.py"], creationflags = subprocess.CREATE_NEW_CONSOLE )
            self.activeNodes.append( pc )

    ########################
    def terminateNode( self, uid ):
        self.managerServer.sendTerminate( uid )

    ########################
    def terminateAllNodes( self ):
        for i in self.activeNodes:
            try:
                i.kill()
            except:
                pass

    ########################
    def enqueueNewTask( self, uid, w, h, numSamplesPerPixel, fileName ):
        hash = random.getrandbits(128)
        th = TaskHeader( str( hash ), "", 0 )    
        self.managerServer.sendNewTask( uid, VRayTracingTask( w, h, numSamplesPerPixel, th ) )
