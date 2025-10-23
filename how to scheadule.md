# How to Schedule the Script on Windows Startup

To have the script run automatically, the best method on Windows is to use the **Task Scheduler**. This will allow you to run the script at set intervals in the background.

Here is a step-by-step guide:

### 1. Open Task Scheduler
*   Press the **Windows Key + R** to open the "Run" dialog.
*   Type `taskschd.msc` and press **Enter**.

### 2. Create a New Task
*   In the "Actions" pane on the right, click on **Create Task...** (this gives you more options than "Create Basic Task").

### 3. Configure the General Tab
*   **Name:** Give the task a descriptive name, like `Desktop Organizer`.
*   **Description:** (Optional) Add a short description, e.g., `Automatic desktop file organization`.
*   Select **"Run whether user is logged on or not"**. This ensures the script runs even if you are not logged in. You may be prompted for your password when you save the task.
*   Check the box for **"Run with highest privileges"**.

### 4. Set up the Trigger
*   Go to the **Triggers** tab and click **New...**.
*   Configure the trigger to run periodically. A good approach is to run the task frequently and let the script's internal schedule decide if it needs to act.
    *   Begin the task: **On a schedule**
    *   Settings: **Daily**
    *   Under "Advanced settings", check **"Repeat task every"** and set it to **1 hour** for a duration of **Indefinitely**.
*   Click **OK**.

### 5. Define the Action
*   Go to the **Actions** tab and click **New...**.
*   **Action:** Select **Start a program**.
*   **Program/script:** You need to provide the full path to your Python executable (`python.exe`).
    *   *To find this path, open Command Prompt and type `where python`. Copy the path that appears.*
*   **Add arguments (optional):** This is where you specify the script and the background flag. Use the full path to your script:
    `"D:\Робочі столи\Робочий стіл 2025\Робочий стіл 01-05-2025 16-08\Оновлений прогамний комплекс\v4.2.py" --background-run`
*   *Note: This flag starts a background process that will check the schedule and, if conditions are met, launch the main application in visual mode to perform the task.*
*   **Start in (optional):** It's important to set this to the directory where your script is located. This ensures that any relative paths in the script work correctly.
    `"D:\Робочі столи\Робочий стіл 2025\Робочий стіл 01-05-2025 16-08\Оновлений прогамний комплекс\"`
*   Click **OK**.

### 6. Adjust Conditions and Settings
*   **Conditions Tab:** You can uncheck options like **"Start the task only if the computer is on AC power"** if you are using a desktop or want it to run on battery.
*   **Settings Tab:** Ensure **"Allow task to be run on demand"** is checked. It's also a good idea to check **"Run task as soon as possible after a scheduled start is missed"**.

### 7. Save the Task
*   Click **OK** to save your new task.
*   You will likely be prompted to enter your Windows user password to grant the necessary permissions.

Your script is now set up to run automatically in the background every hour. The script's own scheduling logic will then determine the exact time to perform the file-moving operation.
