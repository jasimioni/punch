#!/usr/bin/env python3

import yaml
import os
from datetime import datetime, timedelta
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, Container
from textual.widgets import Header, Footer, Static, Label, Input, Button, RadioSet, RadioButton
from textual.screen import ModalScreen
from textual.binding import Binding
from textual.reactive import reactive
from textual.message import Message

# --- Helper: Load Categories ---
def load_categories():
    """Loads categories from categories.yaml or returns defaults."""
    default_cats = {"General": {"short": "gen"}}
    filename = os.path.expanduser("~/.config/punch/punch.yaml")
    
    if not os.path.exists(filename):
        return default_cats

    try:
        with open(filename, 'r') as f:
            data = yaml.safe_load(f)
            return data.get('categories', default_cats)
    except Exception as e:
        return default_cats

# --- Helper: Get Sunday ---
def get_current_week_sunday():
    today = datetime.now().date()
    idx = (today.isoweekday() % 7) 
    return today - timedelta(days=idx)

# --- Confirmation Modal ---
class ConfirmationModal(ModalScreen):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]
    
    def compose(self) -> ComposeResult:
        with Container(id="modal-dialog"):
            yield Label("Delete this time card?", id="modal-label")
            with Horizontal(id="modal-buttons"):
                yield Button("Yes", variant="error", id="yes-btn")
                yield Button("No", variant="primary", id="no-btn")

    def action_cancel(self):
        self.dismiss(False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "yes-btn":
            self.dismiss(True)
        else:
            self.dismiss(False)

class TimeEntryModal(ModalScreen):
    """Modal to select category and enter time."""
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, categories: dict, initial_category: str = None, initial_time: str = ""):
        super().__init__()
        self.categories = categories
        self.initial_category = initial_category
        self.initial_time = initial_time

    def compose(self) -> ComposeResult:
        with Container(id="modal-dialog"):
            yield Label("Select Category:", classes="section-label")
            
            with RadioSet(id="category-radio"):
                for cat_name in self.categories.keys():
                    # Use the custom class here!
                    yield RadioButton(cat_name) 

            yield Label("Enter Minutes:", classes="section-label")
            yield Input(placeholder="e.g. 60", value=self.initial_time, type="integer", id="time-input")
            
            with Horizontal(id="modal-buttons"):
                yield Button("Save", variant="success", id="save-btn")
                yield Button("Cancel", variant="error", id="cancel-btn")

    def on_mount(self):
        """Run once when the modal opens."""
        radio_set = self.query_one("#category-radio", RadioSet)
        
        # 1. Find the target button
        target_button = None
        if self.initial_category:
            for button in radio_set.children:
                if str(button.label) == self.initial_category:
                    target_button = button
                    break
        
        # Default to first button
        if not target_button and radio_set.children:
            target_button = radio_set.children[0]

        # 2. Force focus (which triggers the on_focus auto-select logic)
        if target_button:
            self.call_after_refresh(target_button.focus)

    def action_cancel(self):
        self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit_form()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-btn":
            self._submit_form()
        else:
            self.dismiss(None)

    def _submit_form(self):
        radio_set = self.query_one("#category-radio", RadioSet)
        selected_button = radio_set.pressed_button
        
        if not selected_button:
            self.notify("Please select a category.", severity="error")
            return

        cat_name = str(selected_button.label)
        inp = self.query_one("#time-input", Input)
        
        if inp.value.isdigit():
            self.dismiss((cat_name, int(inp.value)))
        else:
            self.notify("Please enter a valid number for minutes!", severity="error")

# --- Time Card Widget ---
class TimeCard(Static):
    minutes = reactive(0)
    category = reactive("")

    def __init__(self, category: str, minutes: int):
        super().__init__()
        self.category = category
        self.minutes = minutes
        self.can_focus = True

    def compose(self) -> ComposeResult:
        # Display: "Category: 60m"
        yield Label(f"{self.category}\n{self.minutes}m")


    def on_click(self) -> None:
        self.focus()
    
    # Watchers to update label if data changes dynamically
    def watch_minutes(self, val):
        self._update_label()
    
    def watch_category(self, val):
        self._update_label()

    def _update_label(self):
        try:
            self.query_one(Label).update(f"[{self.category}]\n{self.minutes}m")
        except:
            pass

# --- Day Column Widget ---
class DayColumn(Vertical):
    def __init__(self, date_obj, **kwargs):
        super().__init__(**kwargs)
        self.date_obj = date_obj
        self.total_minutes = 0
        self.can_focus = True 

    def compose(self) -> ComposeResult:
        with Vertical(classes="day-header"):
            yield Label(self.date_obj.strftime("%Y-%m-%d"), classes="date-label")
            yield Label("0 min", classes="day-total-label")
        yield Vertical(classes="cards-container")

    def add_entry(self, category: str, minutes: int):
        container = self.query_one(".cards-container")
        card = TimeCard(category, minutes)
        container.mount(card)
        card.scroll_visible()
        self.update_total()

    def update_total(self):
        cards = self.query(TimeCard)
        self.total_minutes = sum(c.minutes for c in cards)
        self.query_one(".day-total-label", Label).update(f"{self.total_minutes} min")
        self.post_message(self.StatsUpdated())

    class StatsUpdated(Message):
        pass

# --- Main Application ---
class TimeSheetApp(App):
    CSS = """
    Screen { align: center middle; }
    #week-grid { height: 100%; width: 100%; align: center top; }
    
    DayColumn {
        width: 1fr;
        height: 100%;
        border-right: solid $primary-background-lighten-2;
    }
    
    DayColumn:focus {
        background: $surface-lighten-1;
        border: thick $accent;
    }

    .day-header {
        height: auto;
        background: $accent;
        color: $text;
        align: center middle;
        padding: 1;
        text-align: center;
        text-style: bold;
    }

    .cards-container { height: 1fr; padding: 1; }

    TimeCard {
        height: auto;
        min-height: 2;
        margin-bottom: 0;
        background: $panel;
        border: solid $background;
        content-align: center middle;
        padding: 0;
    }

    TimeCard:focus {
        border: solid $success;
        background: $surface;
    }

    /* Modal Styling */
    #modal-dialog {
        grid-size: 2;
        grid-gutter: 1;
        grid-rows: auto auto 1fr auto; /* Adaptive rows */
        padding: 1 2;
        width: 60;
        height: auto;
        min-height: 20;
        border: thick $background 80%;
        background: $surface;
    }
    
    .section-label {
        width: 100%;
        margin-top: 1;
        text-style: bold;
    }

    #category-radio {
        height: auto;
        max-height: 10;
        overflow-y: auto;
        background: $surface-darken-1;
        padding: 1;
        margin-bottom: 1;
    }

    #modal-buttons { align: center bottom; height: auto; margin-top: 1; }
    Button { margin: 1; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("down", "focus_next", "Next", show=False),      
        Binding("up", "focus_previous", "Prev", show=False),    
        Binding("left", "move_left", "Left"),
        Binding("right", "move_right", "Right"),
        Binding("a", "add_card", "Add Card"),
        Binding("enter", "handle_enter", "Select/Edit"),
        Binding("d", "delete_card", "Delete Card"),
        Binding("e", "edit_card", "Edit Card"),
    ]

    total_week_minutes = reactive(0)
    categories = {}

    def on_load(self):
        # Load categories before app starts
        self.categories = load_categories()

    def compose(self) -> ComposeResult:
        yield Header()
        start_date = get_current_week_sunday()
        columns = []
        for i in range(7):
            current_date = start_date + timedelta(days=i)
            columns.append(DayColumn(current_date, id=f"day-{i}"))

        yield Horizontal(*columns, id="week-grid")
        yield Footer()

    def on_mount(self):
        self.query_one("#day-1").focus()

    def on_day_column_stats_updated(self, message: DayColumn.StatsUpdated):
        total = sum(col.total_minutes for col in self.query(DayColumn))
        self.total_week_minutes = total

    def watch_total_week_minutes(self, value: int):
        self.sub_title = f"Weekly Total: {value} minutes"

    # --- Actions ---

    def action_handle_enter(self):
        focused = self.screen.focused
        if isinstance(focused, TimeCard):
            self.action_edit_card()
        elif isinstance(focused, DayColumn):
            self.action_add_card()

    def action_add_card(self):
        focused = self.screen.focused
        if not focused: return
        
        target_column = None
        if isinstance(focused, DayColumn):
            target_column = focused
        elif isinstance(focused, TimeCard):
            target_column = focused.parent.parent
        
        if target_column:
            # Check result expects tuple (category, minutes)
            def check_result(result):
                if result:
                    cat, mins = result
                    target_column.add_entry(cat, mins)
                    self.notify(f"Added {cat}: {mins}m", title="Success")
            
            # Pass categories to modal
            self.push_screen(TimeEntryModal(self.categories), check_result)

    def action_edit_card(self):
        focused = self.screen.focused
        if isinstance(focused, TimeCard):
            column = focused.parent.parent
            
            def check_result(result):
                if result:
                    cat, mins = result
                    focused.category = cat
                    focused.minutes = mins
                    column.update_total()
                    self.notify("Updated card")

            # Pass existing values for editing
            self.push_screen(
                TimeEntryModal(self.categories, focused.category, str(focused.minutes)), 
                check_result
            )

    def action_delete_card(self):
        focused = self.screen.focused
        if isinstance(focused, TimeCard):
            def check_confirm(should_delete: bool):
                if should_delete:
                    column = focused.parent.parent
                    focused.remove()
                    column.update_total()
                    self.notify("Deleted entry", severity="warning")
            
            self.push_screen(ConfirmationModal(), check_confirm)

    def action_move_left(self): self.move_column(-1)
    def action_move_right(self): self.move_column(1)

    def move_column(self, direction):
        focused = self.screen.focused
        
        # Safety check: if focus is lost, reset to Monday
        if not focused or focused == self.screen:
            self.query_one("#day-1").focus()
            return

        # Identify which column we are currently in
        current_col = None
        if isinstance(focused, DayColumn):
            current_col = focused
        elif isinstance(focused, TimeCard):
            current_col = focused.parent.parent

        # Calculate new index and focus the TARGET COLUMN only
        if current_col:
            try:
                idx = int(current_col.id.split("-")[1])
                new_idx = idx + direction
                
                # Check bounds (0=Sunday ... 6=Saturday)
                if 0 <= new_idx <= 6:
                    target = self.query_one(f"#day-{new_idx}")
                    target.focus()  # <--- CHANGED: Always focus the column, never the cards
            except:
                pass

if __name__ == "__main__":
    app = TimeSheetApp()
    app.run()