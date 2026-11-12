"""Gateway transport fault injection, without listeners, keys, or network I/O.

These tests cover the confirmed downstream-cancellation bug. They do not claim
to resolve every intermittent Signed GET failure observed in the live tunnel.
"""
from email.message import Message
import http.client
from io import BytesIO
import json
import re
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from demo_staging.tailnet_assertion import verify_request
from scripts import tailnet_sso_gateway as gateway


HOST="test-machine.example.ts.net:10500"
LOGIN="allowed@example.com"
SECRET=b"offline-gateway-transport-test-key-not-a-live-credential"
BODY=b'{"ok":true}'


class Sink(BytesIO):
    def __init__(self,fail_write=None,error=BrokenPipeError):
        super().__init__();self.calls=0;self.fail_write=fail_write;self.error=error

    def write(self,data):
        self.calls+=1
        if self.calls==self.fail_write:
            raise self.error("PRIVATE_EXCEPTION_MESSAGE_MUST_NOT_BE_LOGGED")
        return super().write(data)


def handler(*,method="GET",headers=None,body=b"",address="127.0.0.1",sink=None):
    value=gateway.Gateway.__new__(gateway.Gateway)
    value.server=SimpleNamespace(expected_host=HOST,target_port=19100,secret=SECRET,
        allowed_users={LOGIN:{"actor":"fixture_owner","role":"admin"}})
    value.client_address=(address,12345)
    value.command=method
    value.path="/demo/api/capabilities?PRIVATE_QUERY_DO_NOT_LOG=yes"
    value.requestline=f"{method} {value.path} HTTP/1.1"
    value.request_version="HTTP/1.1"
    value.headers=Message()
    for key,val in (headers if headers is not None else [("Host",HOST),("Tailscale-User-Login",LOGIN)]):
        value.headers[key]=val
    value.rfile=BytesIO(body)
    value.wfile=sink if sink is not None else Sink()
    return value


def install_upstream(monkeypatch,*,phase=None,error=ConnectionResetError,status=200,body=BODY):
    state={"constructs":0,"requests":[],"closes":0}
    def maybe_fail(name):
        if phase==name:
            raise error("PRIVATE_EXCEPTION_MESSAGE_MUST_NOT_BE_LOGGED")
    class Response:
        def __init__(self):self.status=status
        def read(self):
            maybe_fail("read");return body
        def getheaders(self):
            return [("Content-Type","application/json"),("Content-Length","999"),
                ("Connection","keep-alive"),("Server","private-upstream-name")]
    class Connection:
        def __init__(self,host,port,timeout):
            state["constructs"]+=1
            assert (host,port,timeout)==("127.0.0.1",19100,330)
            maybe_fail("connect")
        def request(self,*args,**kwargs):
            state["requests"].append((args,kwargs));maybe_fail("request")
        def getresponse(self):
            maybe_fail("response");return Response()
        def close(self):
            state["closes"]+=1;maybe_fail("close")
    monkeypatch.setattr(gateway.http.client,"HTTPConnection",Connection)
    return state


def diagnostics(capsys):
    text=capsys.readouterr().out
    for secret in (LOGIN,"fixture_owner",SECRET.decode(),"PRIVATE_QUERY_DO_NOT_LOG",
                   "PRIVATE_EXCEPTION_MESSAGE_MUST_NOT_BE_LOGGED","private-upstream-name"):
        assert secret not in text
    values=[json.loads(line.removeprefix("IT_TEM_TAILNET_TRANSPORT ")) for line in text.splitlines()
            if line.startswith("IT_TEM_TAILNET_TRANSPORT ")]
    for value in values:
        assert set(value)=={"request_id","phase","error_class","elapsed_ms"}
        assert re.fullmatch(r"[0-9a-f]{32}",value["request_id"])
        assert type(value["elapsed_ms"]) is int and value["elapsed_ms"]>=0
    return values


@pytest.mark.parametrize("phase,expected_phase",[("connect","upstream_connect"),
    ("request","upstream_request"),("response","upstream_response_headers"),
    ("read","upstream_response_body")])
@pytest.mark.parametrize("error",[ConnectionRefusedError,TimeoutError,http.client.RemoteDisconnected])
def test_upstream_failure_sends_one_502_and_always_closes(monkeypatch,capsys,phase,expected_phase,error):
    state=install_upstream(monkeypatch,phase=phase,error=error)
    value=handler()
    value.forward()
    wire=value.wfile.getvalue()
    assert wire.count(b"HTTP/1.0 ")==1 and wire.startswith(b"HTTP/1.0 502 ")
    assert json.loads(wire.split(b"\r\n\r\n",1)[1])=={"detail":"IT-TEM QA upstream unavailable"}
    assert state["closes"]==(0 if phase=="connect" else 1)
    assert len(state["requests"])==(0 if phase=="connect" else 1)
    events=diagnostics(capsys)
    assert len(events)==1 and events[0]["phase"]==expected_phase
    assert events[0]["error_class"]==error.__name__


@pytest.mark.parametrize("error",[BrokenPipeError,ConnectionResetError])
@pytest.mark.parametrize("failed_write",[1,2])
def test_client_abort_after_200_never_sends_second_response(monkeypatch,capsys,error,failed_write):
    state=install_upstream(monkeypatch)
    sink=Sink(fail_write=failed_write,error=error)
    value=handler(sink=sink)
    value.forward()
    wire=sink.getvalue()
    assert b"502" not in wire and wire.count(b"HTTP/1.0 ")==failed_write-1
    assert sink.calls==failed_write and state["closes"]==1
    events=diagnostics(capsys)
    assert len(events)==1 and events[0]["phase"]=="downstream_response"
    assert events[0]["error_class"]==error.__name__


def test_client_abort_while_sending_upstream_failure_does_not_retry_response(monkeypatch,capsys):
    state=install_upstream(monkeypatch,phase="response",error=TimeoutError)
    sink=Sink(fail_write=1)
    handler(sink=sink).forward()
    assert sink.calls==1 and state["closes"]==1
    events=diagnostics(capsys)
    assert [e["phase"] for e in events]==["upstream_response_headers","downstream_error_response"]
    assert len({e["request_id"] for e in events})==1


def test_close_failure_keeps_successful_response_and_logs_safe_phase(monkeypatch,capsys):
    state=install_upstream(monkeypatch,phase="close")
    value=handler();value.forward()
    assert value.wfile.getvalue().startswith(b"HTTP/1.0 200 ") and state["closes"]==1
    assert [e["phase"] for e in diagnostics(capsys)]==["upstream_close"]


def test_write_request_is_never_replayed_after_ambiguous_response(monkeypatch,capsys):
    state=install_upstream(monkeypatch,phase="response",error=http.client.RemoteDisconnected)
    value=handler(method="POST",body=b"{}",headers=[("Host",HOST),
        ("Tailscale-User-Login",LOGIN),("Content-Length","2")])
    value.forward()
    assert len(state["requests"])==1 and state["requests"][0][0]==("POST",value.path)
    assert value.wfile.getvalue().startswith(b"HTTP/1.0 502 ") and state["closes"]==1
    assert [e["phase"] for e in diagnostics(capsys)]==["upstream_response_headers"]


def test_head_preserves_status_and_never_writes_payload(monkeypatch,capsys):
    state=install_upstream(monkeypatch)
    value=handler(method="HEAD");value.forward()
    wire=value.wfile.getvalue()
    assert wire.startswith(b"HTTP/1.0 200 ") and wire.endswith(b"\r\n\r\n")
    assert BODY not in wire and value.wfile.calls==1 and state["closes"]==1
    assert diagnostics(capsys)==[]


def test_auth_filtering_exact_path_signature_and_backend_csrf403_preserved(monkeypatch,capsys):
    state=install_upstream(monkeypatch,status=403,body=b'{"detail":"CSRF origin denied"}')
    value=handler(method="POST",body=b"{}",headers=[("Host",HOST),("Tailscale-User-Login",LOGIN),
        ("Content-Length","2"),("Origin","https://evil.invalid"),
        ("X-ITTem-Tailnet-Actor","forged_actor"),("Tailscale-User-Name","forged_name"),
        ("X-Forwarded-Proto","http"),("Connection","keep-alive")])
    value.forward()
    args,kwargs=state["requests"][0]
    assert args==("POST",value.path) and kwargs["body"]==b"{}"
    headers={k.lower():v for k,v in kwargs["headers"].items()}
    assert headers["origin"]=="https://evil.invalid" and headers["connection"]=="close"
    assert headers["x-forwarded-proto"]=="https"
    assert not any(k.startswith("tailscale-") for k in headers)
    path,query=value.path.split("?",1)
    request=Request({"type":"http","method":"POST","raw_path":path.encode(),
        "path":path,"query_string":query.encode(),"headers":[(k.encode(),v.encode()) for k,v in headers.items()]})
    assert verify_request(request,SECRET,{"fixture_owner":"admin"},expected_host=HOST)==("fixture_owner","admin")
    wire=value.wfile.getvalue()
    assert wire.startswith(b"HTTP/1.0 403 ") and b"CSRF origin denied" in wire
    assert b"private-upstream-name" not in wire and b"Content-Length: 999" not in wire
    assert state["closes"]==1 and diagnostics(capsys)==[]


@pytest.mark.parametrize("method",["GET","HEAD"])
@pytest.mark.parametrize("address,headers,status",[
    ("198.51.100.5",[("Host",HOST),("Tailscale-User-Login",LOGIN)],403),
    ("127.0.0.1",[("Host",HOST)],403),
    ("127.0.0.1",[("Host",HOST),("Tailscale-User-Login",LOGIN),("Tailscale-User-Login",LOGIN)],403),
    ("127.0.0.1",[("Host",HOST),("Tailscale-User-Login","unknown@example.com")],403),
    ("127.0.0.1",[("Host","foreign.example"),("Tailscale-User-Login",LOGIN)],403),
    ("127.0.0.1",[("Host",HOST),("Tailscale-User-Login",LOGIN),("Transfer-Encoding","chunked")],400),
])
def test_identity_and_ingress_denials_never_open_upstream(monkeypatch,method,address,headers,status):
    state=install_upstream(monkeypatch)
    value=handler(method=method,address=address,headers=headers);value.forward()
    assert value.wfile.getvalue().startswith(f"HTTP/1.0 {status} ".encode())
    if method=="HEAD":
        assert value.wfile.getvalue().endswith(b"\r\n\r\n")
    assert state["constructs"]==0


def test_real_listener_uses_burst_backlog_without_changing_identity_or_request_handling():
    # Real ephemeral loopback listener, not a Provider/server fixture. The
    # production class (also used by run()) must retain the exact Gateway and
    # default thread behaviour while avoiding Python 3.12's five-accept queue.
    with gateway.GatewayHTTPServer(('127.0.0.1',0),gateway.Gateway) as server:
        assert server.request_queue_size>=128
        assert server.RequestHandlerClass is gateway.Gateway
        assert server.server_address[0]=='127.0.0.1'
        assert server.daemon_threads is True
