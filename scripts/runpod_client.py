"""Authenticated Jupyter REST/WebSocket transport; no additional public port."""
import json
import http.cookiejar
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

CLIENT_AGENT="GrowPathLocalDashboard/1.0"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        before=urllib.parse.urlsplit(req.full_url)
        after=urllib.parse.urlsplit(urllib.parse.urljoin(req.full_url,newurl))
        if (before.scheme,before.netloc)!=(after.scheme,after.netloc):
            raise RuntimeError("Jupyter redirected to another host; check the server URL")
        return super().redirect_request(req,fp,code,msg,headers,newurl)


class JupyterHTTPError(RuntimeError):
    def __init__(self,code,path,method):
        self.code=code
        super().__init__(f"Jupyter HTTP {code} ({method} {path.split('?')[0]}); check Jupyter login credentials")


class RunPodClient:
    def __init__(self, url, token, remote_path="workspace/qwen_factory"):
        parts = urllib.parse.urlsplit(url.strip())
        if parts.scheme != "https" or not parts.netloc or parts.username or parts.password:
            raise ValueError("Use the HTTPS Jupyter URL without credentials")
        self.url = urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path.split("/lab")[0].rstrip("/"), "", ""))
        token=token.strip()
        if not token or any(c in token for c in "\r\n"):
            raise ValueError("Enter the Jupyter login token")
        self.token = token
        self.remote_path = remote_path.strip("/")
        self.cookies=http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(NoRedirect(),urllib.request.HTTPCookieProcessor(self.cookies))
        self.opener.addheaders=[("User-Agent",CLIENT_AGENT),("Accept","text/html,application/json;q=0.9,*/*;q=0.8")]
        self.cookie_auth=False
        self.kernel_id = None

    def xsrf(self):
        request=urllib.request.Request(self.url+"/api/kernels")
        self.cookies.add_cookie_header(request)
        for part in request.get_header("Cookie","").split(";"):
            name,_,value=part.strip().partition("=")
            if name=="_xsrf":
                return urllib.parse.unquote(value.strip('"'))
        return ""

    def login(self):
        # Standard Jupyter login supports both a server token and a password.
        login=self.url+"/login?next="+urllib.parse.quote(urllib.parse.urlsplit(self.url).path+"/lab",safe="")
        try:
            with self.opener.open(urllib.request.Request(login),timeout=30) as response:
                response.read()
            fields={"password":self.token,"_xsrf":self.xsrf()}
            request=urllib.request.Request(login,data=urllib.parse.urlencode(fields).encode(),
                headers={"Content-Type":"application/x-www-form-urlencoded","Referer":login},method="POST")
            with self.opener.open(request,timeout=30) as response:
                response.read()
            self.cookie_auth=True
        except urllib.error.HTTPError as error:
            body=error.read(4096).lower()
            if b"1010" in body and "cloudflare" in error.headers.get("Server","").lower():
                raise RuntimeError("RunPod proxy rejected the client (Cloudflare 1010), before Jupyter authentication.") from None
            if error.code==403 and b"xsrf" in body:
                raise RuntimeError("Jupyter login HTTP 403: XSRF cookie/form validation failed; reconnect to refresh the login session.") from None
            raise RuntimeError(f"Jupyter login HTTP {error.code}. Verify the Pod's JUPYTER_PASSWORD or Jupyter login token; do not use HF_TOKEN or a RunPod API key.") from None
        except urllib.error.URLError:
            raise RuntimeError("Could not reach the Jupyter login page") from None

    def api(self, path, data=None, method="GET"):
        body = json.dumps(data).encode() if data is not None else None
        headers={"Content-Type":"application/json"}
        if not self.cookie_auth:
            headers["Authorization"]="token "+self.token
        if self.xsrf():
            headers["X-XSRFToken"]=self.xsrf()
        req = urllib.request.Request(self.url + path, data=body, method=method,headers=headers)
        try:
            with self.opener.open(req, timeout=30) as response:
                raw = response.read()
            return json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            if error.code == 404:
                raise FileNotFoundError("Jupyter file or kernel not found") from None
            raise JupyterHTTPError(error.code,path,method) from None
        except urllib.error.URLError:
            raise RuntimeError("Could not reach Jupyter; check Pod status and network") from None

    def contents(self, relative, content=None):
        path = self.remote_path + "/" + relative
        endpoint = "/api/contents/" + urllib.parse.quote(path, safe="/")
        if content is None:
            return self.api(endpoint + "?content=1&format=text")
        return self.api(endpoint, {"type": "file", "format": "text", "content": content}, "PUT")

    def connect(self):
        endpoint="/api/contents/" + urllib.parse.quote(self.remote_path, safe="/") + "?content=0"
        try:
            self.api(endpoint)
        except JupyterHTTPError as error:
            if error.code not in (401,403):
                raise
            self.login()
            self.api(endpoint)
        kernel = self.api("/api/kernels", {"name": "python3", "path": self.remote_path}, "POST")
        self.kernel_id = kernel["id"]
        return self.kernel_id

    def ensure_file(self, relative, text):
        try:
            old = self.contents(relative)["content"]
        except FileNotFoundError:
            self.contents(relative, text)
            return
        if old != text:
            raise ValueError("Remote file differs; use a new filename: " + relative)

    def execute(self, code, timeout=45):
        import websocket
        if not self.kernel_id:
            raise RuntimeError("Connect first")
        message_id, session = uuid.uuid4().hex, uuid.uuid4().hex
        wsurl = self.url.replace("https://", "wss://", 1) + f"/api/kernels/{self.kernel_id}/channels?session_id={session}"
        try:
            headers={"User-Agent":CLIENT_AGENT}
            if not self.cookie_auth:
                headers["Authorization"]="token "+self.token
            cookie_request=urllib.request.Request(self.url+"/api/kernels")
            self.cookies.add_cookie_header(cookie_request)
            ws = websocket.create_connection(wsurl, timeout=timeout,
                header=headers,cookie=cookie_request.get_header("Cookie",""),origin=self.url)
        except Exception:
            raise RuntimeError("Jupyter WebSocket connection failed; reconnect and check the token") from None
        request = {"header": {"msg_id": message_id, "username": "qwen-local", "session": session,
                    "msg_type": "execute_request", "version": "5.3"}, "parent_header": {}, "metadata": {},
                   "channel": "shell", "content": {"code": code, "silent": False, "store_history": False,
                    "user_expressions": {}, "allow_stdin": False, "stop_on_error": True}, "buffers": []}
        output = []
        deadline = time.monotonic() + timeout
        replied = idle = False
        try:
            ws.send(json.dumps(request))
            while time.monotonic() < deadline:
                ws.settimeout(max(.1, deadline-time.monotonic()))
                message = json.loads(ws.recv())
                if message.get("parent_header", {}).get("msg_id") != message_id:
                    continue
                kind, content = message.get("msg_type", message.get("header", {}).get("msg_type")), message["content"]
                if kind == "stream":
                    output.append(content["text"])
                elif kind == "error":
                    raise RuntimeError("Remote code failed: " + content.get("ename", "Error"))
                elif kind == "execute_reply":
                    if content.get("status") != "ok":
                        raise RuntimeError("Remote request failed; inspect remote setup")
                    replied = True
                elif kind == "status" and content.get("execution_state") == "idle":
                    idle = True
                if replied and idle:
                    return "".join(output)
            raise TimeoutError("Control request timed out; inspect status before retrying a job")
        finally:
            ws.close()

    def call(self, expression):
        code = "import sys, json, importlib\n" \
            + "sys.path.insert(0, '/workspace/qwen_factory/scripts')\n" \
            + "import runpod_bridge\nimportlib.reload(runpod_bridge)\n" \
            + "try:\n    print('QF_RESULT=' + json.dumps({'ok': True, 'value': " + expression + "}, ensure_ascii=False))\n" \
            + "except Exception as e:\n    print('QF_RESULT=' + json.dumps({'ok': False, 'error': str(e)}))\n"
        output = self.execute(code)
        for line in reversed(output.splitlines()):
            if line.startswith("QF_RESULT="):
                result = json.loads(line[len("QF_RESULT="):])
                if not result["ok"]:
                    raise RuntimeError(result["error"])
                return result["value"]
        raise RuntimeError("No response from control kernel")
