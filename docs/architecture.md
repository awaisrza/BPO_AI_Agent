# Architecture

## What one bot does

A **bot = one concurrent voice line**. Per call it:

1. Receives a connected call from ViciDial (the dialer bridges a live answer).
2. Runs answering-machine detection (AMD) — drops machines fast.
3. Greets and runs the script (state machine).
4. Listens (STT) → reasons (LLM, only when off-script) → speaks (TTS).
5. Qualifies the lead.
6. **Warm-transfers** interested leads to a human closer, OR
7. Dispositions the call in ViciDial and moves on.

## Voice pipeline (Pipecat)

```
ViciDial call ─▶ Transport (audio in)
                   │
                   ▼
              [ VAD / endpointing ]      Silero VAD
                   │
                   ▼
              [ STT ]                    Deepgram Nova-3 (pilot) / faster-whisper (prod)
                   │
                   ▼
              [ Conversation FSM ]       greet → pitch → qualify → transfer/disposition
                   │  (off-script only)
                   ▼
              [ LLM ]                    Gemini 2.5 Flash-Lite
                   │
                   ▼
              [ TTS ]                    Fish Audio (pilot) / Piper+cache (prod)
                   │
                   ▼
              Transport (audio out) ─▶ caller / warm transfer to closer
```

## Unit economics (planning estimates)

- ~3,500 active AI minutes / bot / month at an 8–9 hr single shift.
- Per-active-minute cost: STT ~$0.0077 + TTS ~$0.009 + LLM ~$0.003 + orchestration ~$0.005 ≈ **$0.025/min**.
- Managed COGS ≈ **$88/bot**; self-hosted (STT+TTS + cached audio) ≈ **$12–18/bot**.
- ~40–50 bots per mid GPU (L4/A10), bottlenecked by STT.

## Cost-reduction order (do at scale, not before)

1. Self-host TTS (biggest component) + cache static script audio.
2. Self-host STT (faster-whisper, distilled).
3. Cut active minutes (fast AMD, tight script, instant transfer, VAD).
4. Keep GPUs hot (multi-tenant) — keep the LLM on Gemini.

## Data model

See `dashboard/supabase/schema.sql`. Core tables: `organizations`, `subscriptions`, `bots`,
`campaigns`, `contacts`, `calls`, `usage_events`.
