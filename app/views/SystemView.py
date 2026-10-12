# 官网：https://www.yuturuishi.com
# 微信：yuturuishi
# gitee开源地址：https://gitee.com/yuturuishi/rebucca
# github开源地址：https://github.com/yuturuishi/rebucca
import json
import shutil
import os
import sys
import time
import threading
import subprocess
import tempfile
from app.views.ViewsBase import *
from django.shortcuts import render
from app.utils.OSSystem import OSSystem
from app.utils.GlobalUtils import g_filepath_settings_json, GlobalUtils
from framework.settings import PROJECT_VERSION, PROJECT_FLAG, PROJECT_UA, PROJECT_BUILT, PROJECT_ADMIN_START_TIMESTAMP

def f_readSettings(lang):
    try:
        for encoding in ["utf-8", "gbk"]:
            try:
                with open(g_filepath_settings_json, 'r', encoding=encoding) as f:
                    data = json.load(f)
                # 从 languages 字典中直接获取对应语言的 oem 配置
                languages = data.get("languages", {})
                return languages.get(lang, {}).get("oem", {})
            except Exception as e:
                g_logger.error("f_readSettings() error: %s" % str(e))
        return {}
    except:
        return {}

def f_writeSettings(lang, settings_data):
    for encoding in ["utf-8", "gbk"]:
        try:
            with open(g_filepath_settings_json, 'r', encoding=encoding) as f:
                data = json.load(f)
            
            # 更新 languages 字典中对应语言的 oem 配置
            languages = data.get("languages", {})
            if lang in languages:
                languages[lang]["oem"] = settings_data
            
            with open(g_filepath_settings_json, 'w', encoding=encoding) as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            g_logger.error("f_writeSettings() error: %s"%str(e))
            continue

def config(request):
    lang = f_parseRequestLang(request)
    branding = f_readSettings(lang)
    cfg = g_config.to_dict()
    context = {
        "config": cfg,
        "branding": branding
    }
    return render(request, 'app/system/config.html', context)


def _config_api_payload():
    data = g_config.to_dict()
    # 前端习惯 0/1 开关
    for k in (
        "autoAddStreamProxy", "isEnableLoginCaptcha", "logDebug", "isEnableUpdatePopup",
        "isEnableMediaProxyRtmp", "autoStartMedia", "analysisSharedInference",
        "recordingEnabled",
    ):
        if k in data:
            data[k] = 1 if _bool_web(data.get(k)) else 0
    sip = data.get("sipServer") or {}
    if "autoInviteAfterRecCateLog" in sip:
        sip["autoInviteAfterRecCateLog"] = 1 if _bool_web(sip.get("autoInviteAfterRecCateLog")) else 0
    data["sipServer"] = sip
    return data


def _bool_web(v):
    return v is True or v == 1 or str(v).strip().lower() in ("1", "true", "yes")


def api_openConfig(request):
    ret = False
    msg = LANG_VIEWS_T(request, "msg_unknown_error")

    if request.method == 'GET':
        # 加载配置：同时返回基础配置 + OEM 品牌信息
        __check_ret, __check_msg = f_checkRequestSafe(request)
        if __check_ret:
            try:
                lang = f_parseRequestLang(request)
                branding = f_readSettings(lang)
                data = _config_api_payload()
                ret = True
                msg = LANG_VIEWS_T(request, "msg_success")
                res = {
                    "code": 1000,
                    "msg": msg,
                    "data": data,
                    "config": data,
                    "branding": branding
                }
                g_logger.info("SystemView.openConfig(GET) ok")
                return f_responseJson(res)
            except Exception as e:
                msg = str(e)
        else:
            msg = __check_msg

    elif request.method == 'POST':
        __check_ret, __check_msg = f_checkRequestSafe(request)
        if __check_ret:
            params = f_parsePostParams(request)
            g_logger.info("SystemView.openConfig() params: %s" % str(params))

            try:
                before = g_config.to_dict()
                g_config.save_from_web(params)
                notes = GlobalUtils.apply_runtime_config(before)

                ret = True
                msg = LANG_VIEWS_T(request, "syscfg_save_success")
                hint_parts = []
                if "adminPort" in notes:
                    hint_parts.append(LANG_VIEWS_T(request, "syscfg_hint_admin_port"))
                if "logDebug" in notes:
                    hint_parts.append(LANG_VIEWS_T(request, "syscfg_hint_log_debug"))
                if "zlm" in notes:
                    hint_parts.append(LANG_VIEWS_T(request, "syscfg_hint_zlm"))
                if hint_parts:
                    msg = msg + " " + " ".join(hint_parts)

            except Exception as e:
                msg = str(e)
        else:
            msg = __check_msg
    else:
        msg = LANG_VIEWS_T(request, "msg_method_not_supported")

    res = {
        "code": 1000 if ret else 0,
        "msg": msg
    }
    g_logger.info("SystemView.openConfig() res: %s" % str(res))
    return f_responseJson(res)

def api_openSaveSettings(request):
    ret = False
    msg = LANG_VIEWS_T(request, "msg_unknown_error")

    if request.method == 'POST':
        __check_ret, __check_msg = f_checkRequestSafe(request)
        if __check_ret:
            params = f_parsePostParams(request)
            g_logger.info("SystemView.openSaveSettings() params: %s" % str(params))

            try:
                lang = f_parseRequestLang(request)

                branding_name = str(params.get("name", "")).strip()
                branding_welcome = str(params.get("welcome", "")).strip()
                branding_logo_url = str(params.get("logo_url", "")).strip()
                branding_bottom_name = str(params.get("bottom_name", "")).strip()
                branding_author = str(params.get("author", "")).strip()
                branding_author_link = str(params.get("author_link", "")).strip()
                branding_check_version_download_url = str(params.get("check_version_download_url", "")).strip()
                branding_is_show_author = params.get("is_show_author", False)
                if isinstance(branding_is_show_author, str):
                    branding_is_show_author = branding_is_show_author.lower() in ['true', '1', 'yes']

                settings_data = {
                    "name": branding_name,
                    "welcome": branding_welcome,
                    "logo_url": branding_logo_url,
                    "bottom_name": branding_bottom_name,
                    "is_show_author": branding_is_show_author,
                    "author": branding_author,
                    "author_link": branding_author_link,
                    "check_version_download_url": branding_check_version_download_url
                }

                f_writeSettings(lang, settings_data)
                ret = True
                msg = LANG_VIEWS_T(request, "syscfg_save_oem_success")

            except Exception as e:
                msg = str(e)
        else:
            msg = __check_msg
    else:
        msg = LANG_VIEWS_T(request, "msg_method_not_supported")

    res = {
        "code": 1000 if ret else 0,
        "msg": msg
    }
    g_logger.info("SystemView.openSaveSettings() res: %s" % str(res))
    return f_responseJson(res)

def api_openExportLogs(request):
    # 导出日志
    ret = False
    msg = LANG_VIEWS_T(request, "msg_unknown_error")
    info = {

    }
    request_ip = f_parseRequestIp(request)
    lang = f_parseRequestLang(request)

    export_dir = None
    if request.method == 'POST':
        __check_ret, __check_msg = f_checkRequestSafe(request)
        if __check_ret:
            try:
                params = f_parsePostParams(request)
                g_logger.info("SystemView.openExportLogs() params:%s" % str(params))

                g_gb28181SipServer.log_status()
                run_errors = []

                # 导出外层文件夹
                export_dirname = "logs%s-%s-%s" % (PROJECT_VERSION, PROJECT_FLAG, datetime.now().strftime("%Y%m%d%H%M%S"))
                export_dir = os.path.join(g_config.storageTempDir, export_dirname)
                export_filename = "%s.xclogs" % export_dirname
                export_filepath = os.path.join(g_config.storageTempDir, export_filename)

                if not os.path.exists(export_dir):
                    os.makedirs(export_dir)

                osSystem = OSSystem()


                try:
                    # 压缩log文件夹->log.tar
                    log_dir = os.path.join(BASE_DIR, "log")
                    if os.path.exists(log_dir):
                        log_tar_filepath = os.path.join(export_dir, "log")
                        shutil.make_archive(log_tar_filepath, 'tar', log_dir)
                except Exception as e:
                    run_errors.append("export log error:%s" % str(e))

                # 写入config.json, settings.json
                if os.path.exists(g_filepath_config_json):
                    dst = os.path.join(export_dir, "config.json")
                    shutil.copyfile(g_filepath_config_json, dst)

                if os.path.exists(g_filepath_settings_json):
                    dst = os.path.join(export_dir, "settings.json")
                    shutil.copyfile(g_filepath_settings_json, dst)


                if os.path.exists(g_config.mediaStartConfigPath):
                    dst = os.path.join(export_dir, "config.ini")
                    shutil.copyfile(g_config.mediaStartConfigPath, dst)

                allowed_hosts_src = os.path.join(BASE_DIR, ".allowed_hosts")
                if os.path.exists(allowed_hosts_src):
                    allowed_hosts_dst = os.path.join(export_dir, ".allowed_hosts")
                    shutil.copyfile(allowed_hosts_src, allowed_hosts_dst)


                # 写入env.txt
                export_filepath_env = os.path.join(export_dir, "env.txt")
                env_f = open(export_filepath_env, 'w', encoding="utf-8")
                env_f.write("name=%s\n" % PROJECT_UA)
                env_f.write("built=%s\n" % PROJECT_BUILT)
                env_f.write("version=%s\n" % PROJECT_VERSION)
                env_f.write("flag=%s\n" % PROJECT_FLAG)
                env_f.write("log_filename=%s\n" % export_filename)
                env_f.write("app_start_date=%s\n" % datetime.fromtimestamp(PROJECT_ADMIN_START_TIMESTAMP).strftime('%Y-%m-%d %H:%M'))
                env_f.write("current_date=%s\n" % datetime.now().strftime('%Y-%m-%d %H:%M'))
                env_f.write("system=%s\n" % osSystem.getSystemName())
                env_f.write("machine=%s\n" % osSystem.getMachineNode())
                env_f.write("uname_a=%s\n" % osSystem.getMachineUnameA())
                env_f.write("zlm.threadsLoad=%s\n" % str(g_zlm.getThreadsLoad()))
                env_f.write("cpu=%s\n" % osSystem.getMachineCpu())
                env_f.write("nvidia=%s\n" % osSystem.getMachineNvidia())
                env_f.write("ascend=%s\n" % osSystem.getMachineAscend())
                env_f.write("rknpu=%s\n" % osSystem.getMachineRknpu())
                env_f.write("os=%s\n" % str(osSystem.getOSInfo()))
                env_f.write("os_release=%s\n" % osSystem.getMachineOsRelease())
                env_f.write("lscpu=%s\n" % osSystem.getMachineLsCpu())
                env_f.close()

                # 写入online.txt
                export_filepath_online = os.path.join(export_dir, "online.txt")
                online_f = open(export_filepath_online, 'w', encoding="utf-8")
                run_info = {}
                for k, v in run_info.items():
                    online_f.write("%s=%s\n" % (str(k), str(v)))

                online_f.write("av_log=%s\n" % str(g_database.select("select * from av_log order by id desc limit 100")))
                online_f.write("run_errors=%s\n" % str(run_errors))
                online_f.close()

                # 压缩导出文件夹
                shutil.make_archive(export_filepath.replace(".xclogs", ""), 'tar', export_dir)
                # 重命名为 .xclogs
                tar_filepath = export_filepath.replace(".xclogs", ".tar")
                if os.path.exists(tar_filepath):
                    shutil.move(tar_filepath, export_filepath)

                info["export_filename"] = export_filename
                ret = True
                msg = LANG_VIEWS_T(request, "syscfg_export_log_success")
            except Exception as e:
                msg = str(e)
        else:
            msg = __check_msg
    else:
        msg = LANG_VIEWS_T(request, "msg_method_not_supported")

    g_logger.info("export_dir=%s" % str(export_dir))
    if export_dir:
        try:
            if os.path.exists(export_dir):
                shutil.rmtree(export_dir)
        except Exception as e:
            g_logger.error("e=%s" % str(e))

    res = {
        "code": 1000 if ret else 0,
        "msg": msg,
        "info": info
    }
    g_logger.info("SystemView.openExportLogs() res:%s" % str(res))
    return f_responseJson(res)


def api_openRestart(request):
    """重启服务软件（2026-10-11 新增）。

    流程：
    1. 先分离拉起一个守护进程（server_restarter.py），负责在端口下线后观察
       服务是否自行恢复，超时未恢复则按当前启动命令重新拉起；
    2. 本进程延迟 ~1 秒退出：先干净停掉所有布控分析子进程，再以退出码 3 结束
       （runserver autoreloader 约定：子进程退出码 3 → 父进程自动重载工作进程）。
    浏览器端收到响应后轮询首页，服务恢复即自动刷新。
    """
    ret = False
    msg = LANG_VIEWS_T(request, "msg_unknown_error")
    if request.method == 'POST':
        __check_ret, __check_msg = f_checkRequestSafe(request)
        if __check_ret:
            try:
                if getattr(sys, "frozen", False):
                    return f_responseJson({"code": 0, "msg": "打包运行模式下请在服务器上手动重启软件"})

                # 1) 解析服务端口（优先当前请求 host，兜底 10001）
                port = 0
                try:
                    host = request.get_host()
                    if ":" in host:
                        port = int(host.rsplit(":", 1)[1])
                except Exception:
                    port = 0
                if not port:
                    port = 10001

                # 2) 还原当前启动命令（python manage.py runserver ...）
                argv = [sys.executable] + [str(a) for a in sys.argv]

                # 3) 启动规格写临时文件（避免命令行转义问题）
                spec = {"argv": argv, "cwd": str(BASE_DIR)}
                fd, spec_path = tempfile.mkstemp(prefix="rebucca_restart_", suffix=".json")
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(spec, f)

                # 4) 分离拉起守护进程：等下线(30s) → 观察自恢复(25s) → 未恢复则拉起
                helper = os.path.join(str(BASE_DIR), "app", "utils", "server_restarter.py")
                popen_kwargs = {
                    "cwd": str(BASE_DIR),
                    "stdout": subprocess.DEVNULL,
                    "stderr": subprocess.DEVNULL,
                    "close_fds": True,
                }
                if os.name == "nt":
                    popen_kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED | NEW_GROUP
                else:
                    popen_kwargs["start_new_session"] = True
                subprocess.Popen(
                    [sys.executable, helper, str(port), "30", "25", spec_path],
                    **popen_kwargs
                )

                # 5) 延迟退出：先停干净布控子进程（防孤儿占资源），再 os._exit(3)
                def _do_exit():
                    try:
                        from app.analysis.manager import AnalysisManager
                        m = AnalysisManager()
                        for sid in list(m.list_running()):
                            try:
                                m.stop(sid)
                            except Exception:
                                pass
                    except Exception:
                        pass
                    time.sleep(0.3)
                    os._exit(3)

                threading.Timer(1.0, _do_exit).start()
                ret = True
                msg = LANG_VIEWS_T(request, "msg_success")
                g_logger.info("SystemView.api_openRestart() 重启已受理 port=%s argv=%s" % (port, argv))
            except Exception as e:
                msg = str(e)
                g_logger.error("SystemView.api_openRestart() error:%s" % str(e))
        else:
            msg = __check_msg
    else:
        msg = LANG_VIEWS_T(request, "msg_method_not_supported")
    return f_responseJson({"code": 1000 if ret else 0, "msg": msg})
