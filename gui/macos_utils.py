"""macOS Cocoa helper utilities for process naming and application menu customization."""

import sys
import ctypes
import ctypes.util


def _get_objc():
    """Load libobjc and configure base function signatures."""
    objc_path = ctypes.util.find_library("objc")
    if not objc_path:
        return None
    objc = ctypes.cdll.LoadLibrary(objc_path)

    objc.objc_getClass.restype = ctypes.c_void_p
    objc.objc_getClass.argtypes = [ctypes.c_char_p]

    objc.sel_registerName.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]

    return objc


def _send_msg(objc, target, sel_name, *args, argtypes=None, restype=ctypes.c_void_p):
    """Safely call objc_msgSend with explicit 64-bit argument and return types."""
    if not objc or not target:
        return None
    objc.objc_msgSend.restype = restype
    if argtypes is not None:
        objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p] + list(argtypes)
    else:
        objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    sel = objc.sel_registerName(sel_name.encode("utf-8") if isinstance(sel_name, str) else sel_name)
    return objc.objc_msgSend(target, sel, *args)


def setup_macos_app_name(name: str = "C3D explorer") -> None:
    """
    Set macOS native process and bundle name before QApplication starts.
    Updates:
    1. NSBundle infoDictionary (CFBundleName, CFBundleDisplayName)
    2. NSProcessInfo processName
    3. NSUserDefaults to disable automatic injection of Dictation and Character Palette (Emoji & Symbols)
    """
    if sys.platform != "darwin":
        return
    try:
        objc = _get_objc()
        if not objc:
            return

        NSString = objc.objc_getClass(b"NSString")
        title_str = _send_msg(
            objc,
            NSString,
            "stringWithUTF8String:",
            name.encode("utf-8"),
            argtypes=[ctypes.c_char_p],
        )

        # 1. Update NSBundle infoDictionary so Qt queries this as the application name
        NSBundle = objc.objc_getClass(b"NSBundle")
        mainBundle = _send_msg(objc, NSBundle, "mainBundle")
        if mainBundle:
            infoDict = _send_msg(objc, mainBundle, "infoDictionary")
            if infoDict:
                key_name = _send_msg(
                    objc, NSString, "stringWithUTF8String:", b"CFBundleName", argtypes=[ctypes.c_char_p]
                )
                key_disp = _send_msg(
                    objc, NSString, "stringWithUTF8String:", b"CFBundleDisplayName", argtypes=[ctypes.c_char_p]
                )
                _send_msg(objc, infoDict, "setObject:forKey:", title_str, key_name, argtypes=[ctypes.c_void_p, ctypes.c_void_p])
                _send_msg(objc, infoDict, "setObject:forKey:", title_str, key_disp, argtypes=[ctypes.c_void_p, ctypes.c_void_p])

        # 2. Update NSProcessInfo
        NSProcessInfo = objc.objc_getClass(b"NSProcessInfo")
        info = _send_msg(objc, NSProcessInfo, "processInfo")
        if info:
            _send_msg(objc, info, "setProcessName:", title_str, argtypes=[ctypes.c_void_p])

        # 3. Suppress automatic macOS injections into Edit menu via NSUserDefaults
        NSUserDefaults = objc.objc_getClass(b"NSUserDefaults")
        defaults = _send_msg(objc, NSUserDefaults, "standardUserDefaults")
        if defaults:
            k_dict = _send_msg(objc, NSString, "stringWithUTF8String:", b"NSDisabledDictationMenuItem", argtypes=[ctypes.c_char_p])
            k_pal = _send_msg(objc, NSString, "stringWithUTF8String:", b"NSDisabledCharacterPaletteMenuItem", argtypes=[ctypes.c_char_p])
            _send_msg(objc, defaults, "setBool:forKey:", True, k_dict, argtypes=[ctypes.c_bool, ctypes.c_void_p])
            _send_msg(objc, defaults, "setBool:forKey:", True, k_pal, argtypes=[ctypes.c_bool, ctypes.c_void_p])
    except Exception:
        pass


def clean_macos_edit_menu() -> None:
    """
    Remove macOS-injected items from the Edit menu:
    - AutoFill
    - Start Dictation
    - Emoji & Symbols
    - Trailing/redundant separators
    """
    if sys.platform != "darwin":
        return
    try:
        objc = _get_objc()
        if not objc:
            return

        NSApp = _send_msg(objc, objc.objc_getClass(b"NSApplication"), "sharedApplication")
        if not NSApp:
            return

        mainMenu = _send_msg(objc, NSApp, "mainMenu")
        if not mainMenu:
            return

        menuCount = _send_msg(objc, mainMenu, "numberOfItems", restype=ctypes.c_long)
        for m in range(menuCount):
            menuItem = _send_msg(objc, mainMenu, "itemAtIndex:", m, argtypes=[ctypes.c_long])
            title_ns = _send_msg(objc, menuItem, "title")
            u = _send_msg(objc, title_ns, "UTF8String", restype=ctypes.c_char_p)
            menu_name = u.decode() if u else ""

            if "edit" in menu_name.lower():
                submenu = _send_msg(objc, menuItem, "submenu")
                if not submenu:
                    continue

                unwanted_edit = [
                    "autofill", "auto-fill", "auto fill", "dictation",
                    "emoji & symbols", "special characters", "substitutions",
                    "speech", "spelling", "passwords"
                ]
                itemCount = _send_msg(objc, submenu, "numberOfItems", restype=ctypes.c_long)
                for i in reversed(range(itemCount)):
                    subItem = _send_msg(objc, submenu, "itemAtIndex:", i, argtypes=[ctypes.c_long])
                    sub_title = _send_msg(objc, subItem, "title")
                    su = _send_msg(objc, sub_title, "UTF8String", restype=ctypes.c_char_p)
                    t = su.decode().lower() if su else ""
                    if any(x in t for x in unwanted_edit):
                        _send_msg(objc, submenu, "removeItemAtIndex:", i, argtypes=[ctypes.c_long])

                # Remove trailing separators
                itemCount = _send_msg(objc, submenu, "numberOfItems", restype=ctypes.c_long)
                while itemCount > 0:
                    lastItem = _send_msg(objc, submenu, "itemAtIndex:", itemCount - 1, argtypes=[ctypes.c_long])
                    if _send_msg(objc, lastItem, "isSeparatorItem", restype=ctypes.c_bool):
                        _send_msg(objc, submenu, "removeItemAtIndex:", itemCount - 1, argtypes=[ctypes.c_long])
                        itemCount -= 1
                    else:
                        break

                # Remove consecutive duplicate separators
                prev_is_sep = False
                for i in reversed(range(itemCount)):
                    subItem = _send_msg(objc, submenu, "itemAtIndex:", i, argtypes=[ctypes.c_long])
                    is_sep = _send_msg(objc, subItem, "isSeparatorItem", restype=ctypes.c_bool)
                    if is_sep and prev_is_sep:
                        _send_msg(objc, submenu, "removeItemAtIndex:", i, argtypes=[ctypes.c_long])
                    prev_is_sep = is_sep
    except Exception:
        pass


def clean_macos_menus(
    name: str = "C3D explorer",
    remove_services: bool = True,
    remove_hide_others: bool = True,
) -> None:
    """
    Clean both the native Application Menu and the Edit Menu across the entire macOS menubar.
    """
    if sys.platform != "darwin":
        return
    try:
        objc = _get_objc()
        if not objc:
            return

        NSApp = _send_msg(objc, objc.objc_getClass(b"NSApplication"), "sharedApplication")
        if not NSApp:
            return

        mainMenu = _send_msg(objc, NSApp, "mainMenu")
        if not mainMenu:
            return

        # 1. Clean the Application Menu (Menu 0)
        firstItem = _send_msg(objc, mainMenu, "itemAtIndex:", 0, argtypes=[ctypes.c_long])
        if firstItem:
            submenu = _send_msg(objc, firstItem, "submenu")
            if submenu:
                NSString = objc.objc_getClass(b"NSString")
                title_str = _send_msg(
                    objc,
                    NSString,
                    "stringWithUTF8String:",
                    name.encode("utf-8"),
                    argtypes=[ctypes.c_char_p],
                )
                _send_msg(objc, firstItem, "setTitle:", title_str, argtypes=[ctypes.c_void_p])
                _send_msg(objc, submenu, "setTitle:", title_str, argtypes=[ctypes.c_void_p])

                unwanted_app = ["About Qt"]
                if remove_services:
                    unwanted_app.append("Services")
                if remove_hide_others:
                    unwanted_app.extend(["Hide Others", "Show All"])

                count = _send_msg(objc, submenu, "numberOfItems", restype=ctypes.c_long)
                for i in reversed(range(count)):
                    item = _send_msg(objc, submenu, "itemAtIndex:", i, argtypes=[ctypes.c_long])
                    title_ns = _send_msg(objc, item, "title")
                    u = _send_msg(objc, title_ns, "UTF8String", restype=ctypes.c_char_p)
                    t = u.decode() if u else ""

                    if any(k in t for k in unwanted_app):
                        _send_msg(objc, submenu, "removeItemAtIndex:", i, argtypes=[ctypes.c_long])
                    elif t.startswith("About ") and t != f"About {name}":
                        new_t = _send_msg(
                            objc,
                            NSString,
                            "stringWithUTF8String:",
                            f"About {name}".encode("utf-8"),
                            argtypes=[ctypes.c_char_p],
                        )
                        _send_msg(objc, item, "setTitle:", new_t, argtypes=[ctypes.c_void_p])
                    elif t.startswith("Hide ") and t != f"Hide {name}":
                        new_t = _send_msg(
                            objc,
                            NSString,
                            "stringWithUTF8String:",
                            f"Hide {name}".encode("utf-8"),
                            argtypes=[ctypes.c_char_p],
                        )
                        _send_msg(objc, item, "setTitle:", new_t, argtypes=[ctypes.c_void_p])
                    elif t.startswith("Quit ") and t != f"Quit {name}":
                        new_t = _send_msg(
                            objc,
                            NSString,
                            "stringWithUTF8String:",
                            f"Quit {name}".encode("utf-8"),
                            argtypes=[ctypes.c_char_p],
                        )
                        _send_msg(objc, item, "setTitle:", new_t, argtypes=[ctypes.c_void_p])

                # Remove consecutive or redundant separators in app menu
                count = _send_msg(objc, submenu, "numberOfItems", restype=ctypes.c_long)
                prev_is_sep = True
                for i in reversed(range(count)):
                    item = _send_msg(objc, submenu, "itemAtIndex:", i, argtypes=[ctypes.c_long])
                    is_sep = _send_msg(objc, item, "isSeparatorItem", restype=ctypes.c_bool)
                    if is_sep and prev_is_sep:
                        _send_msg(objc, submenu, "removeItemAtIndex:", i, argtypes=[ctypes.c_long])
                    else:
                        prev_is_sep = is_sep

        # 2. Clean the Edit Menu
        clean_macos_edit_menu()
    except Exception:
        pass
