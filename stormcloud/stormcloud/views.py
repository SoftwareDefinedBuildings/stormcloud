from pyramid.view import view_config
import tempfile
import pyramid.httpexceptions as exc
import base64
import pymongo
import re
import time
from pyramid.response import Response
import subprocess

db = pymongo.MongoClient().stormcloud

@view_config(route_name='register', renderer='json', request_method="POST")
def v_claim(request):
    jq = request.json_body
    if "namespace" not in jq:
            return {"status":"error","message":"missing namespace parameter"}
    if re.match("^[a-z0-9_-]{1,16}$", jq["namespace"]) is None:
        return {"status":"error","message":"namespace fails style nazi rules (^[a-z0-9_-]{1,16}$)"}
    if "key" not in jq:
            return {"status":"error","message":"missing key parameter"}
    if "email" not in jq:
            return {"status":"error","message":"missing email parameter"}
    try:
        with tempfile.NamedTemporaryFile() as tf:
            tf.write(base64.b64decode(jq["key"]))
            tf.flush()
            out = subprocess.check_output(["gpg","--import", "--status-fd","1", tf.name])
            ksig = ""
            for l in out.splitlines():
                if l.split()[0] == "[GNUPG:]" and l.split()[1] == "IMPORT_OK":
                ksig = l.split()[3]
            if len(ksig) != 40:
                return {"status":"error","message":"problem with key"}
            existing_nm = db.namespaces.find_one({"name":jq["namespace"]})
            if existing_nm is None:
                db.namespaces.save({"name":jq["namespace"], "key":ksig, "email":jq["email"]})
                return {"status":"success","message":"new namespace inserted"}
            else:
                if existing_nm["key"] == ksig:
                    return {"status":"success","message":"namespace existed with same key"}
                else:
                    return {"status":"error","message":"namespace exists with different key"}

    except:
        return {"status":"error","message":"internal error"}

@view_config(route_name='publish', renderer='json', request_method="POST")
def v_publish(request):
    jq = request.json_body
    if "namespace" not in jq:
        return {"status":"error","message":"missing namespace parameter"}
    if "signature" not in jq:
        return {"status":"error","message":"missing signature"}
    if "name" not in jq:
        return {"status":"error","message":"missing name"}
    if re.match("^[a-z0-9_\-\.]{2,32}$", jq["name"]) is None:
        return {"status":"error","message":"name fails style nazi rules (^[a-z0-9_\-\.]{2,32}$)"}
    if "sdb" not in jq:
        return {"status":"error","message":"missing sdb"}

    with tempfile.NamedTemporaryFile() as payload:
        with tempfile.NamedTemporaryFile() as signature:
            payload.write(base64.b64decode(jq["sdb"]))
            payload.flush()
            signature.write(base64.b64decode(jq["signature"]))
            signature.flush()
            out = subprocess.check_output(["gpg","--status-fd","1","--verify", signature.name, payload.name])
            for l in out.splitlines():
                ls = l.split()
                if ls[0] == "[GNUPG:]" and ls[1] == "VALIDSIG":
                    k = ls[2]
                    ns = db.namespaces.find_one({"key":k, "name":jq["namespace"]})
                    if ns is None:
                        return {"status":"error","message":"namespace/key incorrect"}
                    else:
                        doc = {"namespace":jq["namespace"],"name":jq["name"], "sdb":jq["sdb"], "ts":time.time()}
                        db.images.save(doc)
                        return {"status":"success","message":"image published", "link":jq["namespace"]+":"+jq["name"]}
            return {"status":"error","message":"signature/namespace verification failed"}

@view_config(route_name='get', request_method="GET")
def v_get(request):
    name = request.matchdict["name"]
    if name is None:
        return None
    img = list(db.images.find({"namespace":request.matchdict["namespace"],"name":name}).sort("ts", pymongo.DESCENDING).limit(1))
    if len(img) == 0:
        return None
    else:
        r = Response(content_type="application/octet-stream", body=base64.b64decode(img[0]["sdb"]))

        return r
