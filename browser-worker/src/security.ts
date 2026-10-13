export class SecurityPolicyError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SecurityPolicyError";
  }
}

export function assertAllowedUrl(rawUrl: string, allowedHosts: string[]): void {
  try {
    const parsed = new URL(rawUrl);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      throw new SecurityPolicyError(
        `Disallowed URL protocol: ${parsed.protocol}. Only http/https permitted.`
      );
    }
    if (allowedHosts.length > 0) {
      const hostname = parsed.hostname;
      const isAllowed = allowedHosts.some(
        (allowed) =>
          hostname === allowed ||
          hostname === allowed.split(":")[0] ||
          allowed === "*"
      );
      if (!isAllowed) {
        throw new SecurityPolicyError(
          `Target host '${hostname}' is not in allowed hosts list: ${JSON.stringify(
            allowedHosts
          )}`
        );
      }
    }
  } catch (err: any) {
    if (err instanceof SecurityPolicyError) throw err;
    throw new SecurityPolicyError(`Invalid target URL '${rawUrl}': ${err.message}`);
  }
}
