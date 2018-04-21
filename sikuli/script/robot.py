import sys
import pyscreenshot  # EXT
import warnings
import platform
import subprocess
from enum import Enum
from time import time
from base64 import b64decode
from io import BytesIO

from PIL import Image as PILImage  # EXT

if sys.version_info >= (3, 0):
    import autopy3 as autopy  # EXT
else:
    import autopy  # EXT

try:
    import devtools  # EXT
except ImportError:
    pass

try:
    import ctypes
    _native = ctypes.CDLL("csikuli.so")
except OSError:
    _native = None


from .image import Image
from .key import Mouse
from .sikulpy import unofficial


import logging
log = logging.getLogger(__name__)


class Platform(Enum):
    WINDOWS = 'Windows'
    LINUX = 'Linux'
    DARWIN = 'Darwin'
    VNC = 'VNC'
    CHROME = 'Chrome'


PLATFORM = Platform(platform.system())


_vnc_server = None
_chrome_server = None  # type: devtools.Client


def setVnc(server):
    global PLATFORM, _vnc_server
    PLATFORM = Platform.VNC
    _vnc_server = server


def setChrome(server):
    global PLATFORM, _chrome_server
    PLATFORM = Platform.CHROME
    _chrome_server = devtools.Client(server)


class Robot(object):
    autopyMouseMap = {
        Mouse.LEFT: autopy.mouse.LEFT_BUTTON,
        Mouse.RIGHT: autopy.mouse.RIGHT_BUTTON,
        Mouse.MIDDLE: autopy.mouse.CENTER_BUTTON,
    }

    chromeMouseMap = {
        Mouse.LEFT: "left",
        Mouse.RIGHT: "right",
        Mouse.MIDDLE: "midle",
    }

    @staticmethod
    def mouseMove(xy):
        """
        :param (int, int) xy:
        """
        log.info("mouseMove(%r)", xy)
        x, y = int(xy[0]), int(xy[1])

        if PLATFORM == Platform.CHROME:
            _chrome_server.mousePos = x, y
            _chrome_server.input.dispatchMouseEvent("mouseMoved", x, y)
        else:
            autopy.mouse.move(x, y)

    @staticmethod
    def mouseDown(button):
        # log.info("mouseDown(%r)", button)
        if PLATFORM == Platform.CHROME:
            x, y = _chrome_server.mousePos
            _chrome_server.input.dispatchMouseEvent(
                "mousePressed", x, y, button=Robot.chromeMouseMap[button])
        else:
            autopy.mouse.toggle(True, Robot.autopyMouseMap[button])

    @staticmethod
    def mouseUp(button):
        # log.info("mouseUp(%r)", button)
        if PLATFORM == Platform.CHROME:
            x, y = _chrome_server.mousePos
            _chrome_server.input.dispatchMouseEvent(
                "mouseReleased", x, y, button=Robot.chromeMouseMap[button])
        else:
            autopy.mouse.toggle(False, Robot.autopyMouseMap[button])

    @staticmethod
    def getMouseLocation():
        """
        :rtype: (int, int)
        """
        if PLATFORM == Platform.CHROME:
            return _chrome_server.mousePos
        else:
            return autopy.mouse.get_pos()

    # keyboard
    @staticmethod
    def keyDown(key):
        log.info("keyDown(%r)", key)
        if PLATFORM == Platform.CHROME:
            _chrome_server.input.dispatchKeyEvent("keyDown", string=key)
        else:
            autopy.key.toggle(key, True)

    @staticmethod
    def keyUp(key):
        log.info("keyUp(%r)", key)
        if PLATFORM == Platform.CHROME:
            _chrome_server.input.dispatchKeyEvent("keyUp", string=key)
        else:
            autopy.key.toggle(key, False)

    @staticmethod
    @unofficial
    def type(text, modifiers):
        log.info("type(%r, %r)", text, modifiers)
        for letter in text:
            if PLATFORM == Platform.CHROME:
                _chrome_server.input.dispatchKeyEvent("char", string=letter)
            else:
                autopy.key.tap(letter, modifiers or 0)

    @staticmethod
    def getClipboard():
        """
        :rtype: str
        """
        if PLATFORM == Platform.LINUX:
            return subprocess.Popen(
                "xclip -o",
                shell=True,
                stdout=subprocess.PIPE
            ).stdout.read().decode("utf8")
        else:
            warnings.warn('Robot.getClipboard() not implemented')  # FIXME
            return ""

    @staticmethod
    @unofficial
    def putClipboard(text):
        """
        :param str text:
        """
        if PLATFORM == Platform.LINUX:
            p = subprocess.run(
                "xclip",
                input=text,
                shell=True,
            )
            p.wait()
        else:
            warnings.warn('Robot.putClipboard() not implemented')  # FIXME

    @staticmethod
    def isLockOn(key):
        """
        :param key:
        :rtype: bool
        """
        warnings.warn('Robot.isLockOn(%r) not implemented' % key)  # FIXME
        return False

    # screen
    @staticmethod
    def getNumberScreens():
        """
        :rtype: int
        """
        if PLATFORM == Platform.LINUX and _native:
            return _native.getNumberScreens()
        elif PLATFORM == Platform.VNC:
            return 1
        elif PLATFORM == Platform.CHROME:
            return 1
        else:
            warnings.warn('Robot.getNumberScreens() not implemented')  # FIXME
        return 1

    @staticmethod
    def screenSize():
        """
        :rtype: (int, int, int, int)
        """
        if PLATFORM == Platform.CHROME:
            img = Robot.capture()
            w, h = img.w, img.h
        else:
            w, h = autopy.screen.get_size()
        return 0, 0, w, h

    @staticmethod
    def capture(bbox=None):
        """
        :param (int, int, int, int) bbox:
        :rtype: Image
        """
        _start = time()

        if PLATFORM == Platform.CHROME:
            js = _chrome_server.page.captureScreenshot()
            raw = b64decode(js['data'])
            data = PILImage.open(BytesIO(raw))
        elif PLATFORM == Platform.LINUX and _native:
            x, y, w, h = bbox

            size = w * h
            objlength = size * 3

            _native.capture.argtypes = []
            result = (ctypes.c_ubyte*objlength)()

            _native.capture(x, y, w, h, result)
            data = PILImage.frombuffer('RGB', (w, h), result, 'raw', 'RGB', 0, 1)
        else:
            bbox2 = (
                bbox[0], bbox[1],
                bbox[0] + bbox[2], bbox[1] + bbox[3]
            )
            data = pyscreenshot.grab(bbox=bbox2, childprocess=False)

        if bbox:
            if data.size[0] == bbox[2] * 2:
                log.debug("Captured image is double size, shrinking")
                data = data.resize((data.size[0]//2, data.size[1]//2))
            elif data.size[0] != bbox[2]:
                log.warning(
                    "Captured image is different size than we expected (%dx%d vs %dx%d)",
                    data.size[0], data.size[1], bbox[2], bbox[3]
                )

        log.info("capture(%r) [%.3fs]", bbox, time() - _start)
        return Image(data)

    # window
    @staticmethod
    def focus(application):
        """
        :param str application:
        """
        if PLATFORM == Platform.DARWIN:
            # FIXME: we don't want to hard-code 'Chrome' as the app, and
            # we want 'window title contains X' rather than 'is X'
            script = b"""
set theTitle to "%s"
tell application "System Events"
    tell process "Chrome"
        set frontmost to true
        perform action "AXRaise" of (windows whose title is theTitle)
    end tell
end tell
""" % application.encode('ascii')
            subprocess.run("osascript", input=script, shell=True)
        elif PLATFORM == Platform.LINUX:
            p = subprocess.Popen(
                "xdotool search --name '%s' windowactivate" % application,
                shell=True
            )
            p.wait()
        elif PLATFORM == Platform.CHROME:
            _chrome_server.focus(application)
        else:
            warnings.warn('App.focus(%r) not implemented for %r' % (application, PLATFORM))  # FIXME
