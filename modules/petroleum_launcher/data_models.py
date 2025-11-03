"""Data models for petroleum launcher automation system"""

from dataclasses import dataclass
from typing import Dict, List, Any, Optional
from datetime import datetime


@dataclass
class ProgramInfo:
    """Information about a detected petroleum program"""
    name: str
    display_name: str
    executable_path: str
    version: str
    install_path: str
    detected: bool = False
    last_check: str = ""
    install_error: Optional[str] = None


@dataclass
class AutomationStep:
    """Single step in an automation workflow"""
    step_type: str  # "launch_program", "open_file", "wait", "run_command", "click_button", "screenshot"
    program_name: str = ""
    file_path: str = ""
    command: str = ""
    parameters: Dict[str, Any] = None
    wait_time: int = 0
    window_position: Dict[str, int] = None
    description: str = ""
    button_text: str = ""  # For click_button steps
    button_position: Dict[str, int] = None  # For click_button steps
    screenshot_description: str = ""  # For screenshot steps

    def __post_init__(self):
        if self.parameters is None:
            self.parameters = {}
        if self.window_position is None:
            self.window_position = {}
        if self.button_position is None:
            self.button_position = {}


@dataclass
class WorkflowStep:
    """Enhanced workflow step for recording-based workflows"""
    step_number: int
    action_type: str  # "click", "input_text", "wait", "launch", "screenshot", "conditional", "loop", "custom_script"
    description: str
    target_element: str
    position: Dict[str, int]
    wait_time: float = 2.0
    optional: bool = False
    screenshot_path: Optional[str] = None
    text_to_input: Optional[str] = None
    program_name: Optional[str] = None
    file_path: Optional[str] = None
    command: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    conditional_logic: Optional[Dict[str, Any]] = None
    loop_logic: Optional[Dict[str, Any]] = None
    script_content: Optional[str] = None
    script_language: Optional[str] = None
    screenshot_description: Optional[str] = None

    def __post_init__(self):
        if self.parameters is None:
            self.parameters = {}
        if self.position is None:
            self.position = {"x": 0, "y": 0}


@dataclass
class Workflow:
    """Complete automation workflow"""
    name: str
    description: str
    steps: List[Any]  # Can be AutomationStep or WorkflowStep
    created_date: str
    modified_date: str
    author: str = ""
    version: str = "1.0"
    software: str = ""
    category: str = ""
    difficulty: str = ""
    estimated_time: float = 0.0
    tags: List[str] = None
    dependencies: List[str] = None
    variables: Dict[str, Any] = None
    error_handling: bool = False
    retry_count: int = 3
    timeout: int = 60

    def __post_init__(self):
        if not self.created_date:
            self.created_date = datetime.now().isoformat()
        if not self.modified_date:
            self.modified_date = datetime.now().isoformat()
        if self.tags is None:
            self.tags = []
        if self.dependencies is None:
            self.dependencies = []
        if self.variables is None:
            self.variables = {}


@dataclass
class ScreenshotRecord:
    """Record of a screenshot with button information"""
    timestamp: str
    image_path: str
    button_text: str
    button_position: Dict[str, int]
    action_description: str
    window_title: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class AutomationAction:
    """Single automation action recorded from user input"""
    action_type: str  # "click", "double_click", "right_click", "drag", "type", "scroll", "wait", "condition", "branch"
    position: Dict[str, int]
    timestamp: str
    description: str
    screenshot_path: Optional[str] = None
    image_template: Optional[str] = None  # For OpenCV template matching
    text_to_type: Optional[str] = None
    scroll_direction: Optional[str] = None
    scroll_amount: Optional[int] = None
    wait_time: Optional[float] = None
    confidence_threshold: float = 0.8
    petroleum_context: Optional[Dict[str, Any]] = None  # Petroleum software specific context
    conditional_logic: Optional[Dict[str, Any]] = None  # Conditional recording data

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class ConditionalAction:
    """Conditional action with decision logic"""
    condition_type: str  # "if_exists", "if_not_exists", "if_text_contains", "if_window_contains", "if_file_exists"
    condition_parameters: Dict[str, Any]
    true_actions: List[AutomationAction]  # Actions to execute if condition is true
    false_actions: List[AutomationAction] = None  # Actions to execute if condition is false (optional)
    description: str = ""
    confidence_threshold: float = 0.8

    def __post_init__(self):
        if self.false_actions is None:
            self.false_actions = []


@dataclass
class WorkflowBranch:
    """Branch point in workflow with multiple paths"""
    branch_id: str
    condition: ConditionalAction
    branch_points: Dict[str, List[AutomationAction]]  # Maps branch names to action lists
    default_branch: str = "true"
    description: str = ""

    def get_actions_for_branch(self, branch_name: str) -> List[AutomationAction]:
        """Get actions for a specific branch"""
        return self.branch_points.get(branch_name, [])


@dataclass
class PetroleumWorkflowTemplate:
    """Pre-built workflow templates for petroleum software"""
    name: str
    software: str  # "petrel", "harmony_enterprise", "kappa", etc.
    description: str
    category: str  # "data_import", "simulation", "analysis", "reporting"
    steps: List[Dict[str, Any]]
    estimated_time: str
    difficulty: str  # "beginner", "intermediate", "advanced"
    prerequisites: List[str]

    def to_workflow(self) -> Workflow:
        """Convert template to workflow"""
        steps = []
        for step_data in self.steps:
            step = AutomationStep(
                step_type=step_data.get('type', 'wait'),
                description=step_data.get('description', ''),
                wait_time=step_data.get('wait_time', 0),
                program_name=step_data.get('program_name', ''),
                file_path=step_data.get('file_path', ''),
                command=step_data.get('command', ''),
                parameters=step_data.get('parameters', {})
            )
            steps.append(step)

        return Workflow(
            name=self.name,
            description=self.description,
            steps=steps,
            created_date=datetime.now().isoformat(),
            modified_date=datetime.now().isoformat(),
            software=self.software,
            category=self.category,
            estimated_time=float(self.estimated_time.replace(' min', '') if 'min' in self.estimated_time else 0),
            dependencies=self.prerequisites
        )


@dataclass
class RecordingSession:
    """Complete recording session with screenshots and automation actions"""
    session_id: str
    description: str
    start_time: str
    end_time: str
    screenshots: List[ScreenshotRecord]
    actions: List[AutomationAction]
    generated_script: Optional[str] = None

    def __post_init__(self):
        if not self.start_time:
            self.start_time = datetime.now().isoformat()
        if not self.end_time:
            self.end_time = datetime.now().isoformat()