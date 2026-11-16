-- AI Fronter — start mod_audio_stream to local SIP edge WebSocket
--
-- Channel vars set by dialplan: agent_user, org_slug, caller, callee
-- Env on FreeSWITCH host: AI_FRONTER_STREAM_HOST (default 127.0.0.1:8790)

local host = os.getenv("AI_FRONTER_STREAM_HOST") or "127.0.0.1:8790"
local agent = session:getVariable("agent_user") or session:getVariable("destination_number") or ""
local org_slug = session:getVariable("org_slug") or ""
local caller = session:getVariable("caller") or session:getVariable("caller_id_number") or ""
local callee = session:getVariable("callee") or session:getVariable("destination_number") or agent
local uuid = session:getVariable("uuid") or ""

if agent == "" then
  freeswitch.consoleLog("ERR", "ai_fronter_stream: missing agent_user\n")
  return
end

local qs = string.format(
  "agent_user=%s&org_slug=%s&caller=%s&callee=%s",
  agent, org_slug, caller, callee
)
local ws_url = string.format("ws://%s/v1/stream/fs?%s", host, qs)

freeswitch.consoleLog("INFO", "ai_fronter_stream: " .. ws_url .. "\n")

-- uuid_audio_stream API: uuid start wss-url mono|mixed|stereo 8k|16k [metadata]
local cmd = string.format("%s start %s mono 8k", uuid, ws_url)
local api = freeswitch.API()
local result = api:execute("uuid_audio_stream", cmd)
freeswitch.consoleLog("INFO", "ai_fronter_stream result: " .. (result or "") .. "\n")

-- Keep call alive while streaming (mod_audio_stream owns media until hangup)
session:streamFile("silence_stream://-1")
