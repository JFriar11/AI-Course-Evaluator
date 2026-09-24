# Ollama Client Installation on Windows
## Prerequisites
- Windows 10 or later (64-bit recommended)
- Administrator access for installation
## Install Ollama
1. Open the official download page: <https://ollama.com/download/windows>.
2. Download the Windows installer.
3. Run the downloaded installer and follow the prompts.
4. Restart Windows if the installer requests it.
Ollama normally runs as a background application after installation. Its command-line client is available through PowerShell or Command Prompt.
## Verify the Installation
Open PowerShell and run:
```powershell
ollama --version
```
If a version number is displayed, the installation was successful. If the command is not recognized, restart the terminal or Windows and try again.
## Download and Run a Model
Download a model, such as `deepseek-r1:8b`:
```powershell
ollama pull deepseek-r1:8b
```
Start an interactive chat:
```powershell
ollama run deepseek-r1:8b
```
Enter a prompt, then press `Ctrl+C` to exit.
## Useful Commands
```powershell
ollama list                  # List downloaded models
ollama ps                    # List running models
ollama stop deepseek-r1:8b         # Stop a running model
ollama rm deepseek-r1:8b           # Remove a downloaded model
ollama serve                 # Start the Ollama service manually
```
## Local API
Ollama's local API is available at `http://localhost:11434` while Ollama is running. For example, test it with PowerShell:
```powershell
Invoke-RestMethod http://localhost:11434/api/tags
```
## Troubleshooting
- Ensure the Ollama application is running in the system tray.
- Restart PowerShell after installing Ollama so the updated `PATH` is loaded.
- Confirm that Windows Defender Firewall permits Ollama when prompted.
- Check available disk space before downloading large models.
- Use `ollama list` to confirm that a model downloaded successfully.

