/** Parse E.164 or loose dial strings into ViciDial phone_code + phone_number. */
export function parseDialPhone(input: string): { phone_code: string; phone_number: string } {
  const trimmed = input.trim();
  if (!trimmed) {
    throw new Error("Phone number is required.");
  }

  const digits = trimmed.replace(/\D/g, "");
  if (digits.length < 10) {
    throw new Error("Enter a full phone number with country code (e.g. +923142222318).");
  }

  // Pakistan: +92 followed by 10-digit mobile (3xx…)
  if (digits.startsWith("92") && digits.length >= 12) {
    return { phone_code: "92", phone_number: digits.slice(2) };
  }

  // US/Canada: 10 digits or 1 + 10 digits
  if (digits.length === 10) {
    return { phone_code: "1", phone_number: digits };
  }
  if (digits.length === 11 && digits.startsWith("1")) {
    return { phone_code: "1", phone_number: digits.slice(1) };
  }

  // Generic international: country code = prefix before last 10 digits
  if (digits.length > 10) {
    return {
      phone_code: digits.slice(0, -10),
      phone_number: digits.slice(-10),
    };
  }

  throw new Error("Could not parse phone number — include country code (e.g. +92…).");
}

/** Normalize caller ID for Telnyx/ViciDial — E.164 with leading + (required for outbound SIP). */
export function formatOutboundCid(input: string): string {
  const digits = input.trim().replace(/\D/g, "");
  if (digits.length < 10) {
    throw new Error("Outbound caller ID must be at least 10 digits (e.g. +19482194316).");
  }
  if (digits.length === 10) {
    return `+1${digits}`;
  }
  if (digits.length === 11 && digits.startsWith("1")) {
    return `+${digits}`;
  }
  return `+${digits}`;
}
