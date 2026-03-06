# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 0.7.x   | ✅ Current release |
| < 0.7   | ❌ No patches      |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, report them via email:

📧 **dushyantgarg3@gmail.com**

Please include:

- A description of the vulnerability
- Steps to reproduce the issue
- Affected version(s)
- Any potential impact you've identified

## Disclosure Timeline

- **Acknowledgement:** Within 48 hours of report
- **Initial assessment:** Within 7 days
- **Fix target:** Within 30 days for confirmed vulnerabilities
- **Public disclosure:** After a fix is available, coordinated with the reporter

## Scope

agentplan is a local CLI tool that stores data in a SQLite database. The primary security concerns are:

- **Command injection** via agent command templates (`{ticket}`, `{prompt}` placeholders)
- **Path traversal** in project directory configuration
- **SQL injection** in CLI inputs

## Security Best Practices

- Pin agentplan to a specific version in production workflows
- Review agent command templates before use — they execute shell commands
- Use the `--dry-run` flag to preview operations before committing changes
