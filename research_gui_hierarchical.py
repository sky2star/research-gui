import sys
import yaml
import uuid
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout,
    QTreeWidget, QTreeWidgetItem, QTreeWidgetItemIterator,  # <--- 在这里添加
    QLabel, QLineEdit, QTextEdit,
    QStatusBar, QMenuBar, QFormLayout, QScrollArea, QMessageBox, QMenu,
    QToolBar
)

from PyQt6.QtGui import QAction, QFont
from PyQt6.QtCore import Qt

# --- 全局变量 ---
# 使用新的层级化数据文件
DATA_FILE = Path("project_tree_hierarchical.yaml")

class ResearchTreeWidget(QTreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        # 启用拖放来重新排序
        self.setDragDropMode(QTreeWidget.DragDropMode.InternalMove)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)

    def contextMenuEvent(self, event):
        """增强的右键菜单，支持添加同级和子任务。"""
        context_menu = QMenu(self)
        selected_item = self.itemAt(event.pos())

        # 添加动作
        add_sibling_action = QAction("➕ Add Sibling Task", self)
        add_child_action = QAction("➕ Add Child Task", self)
        delete_action = QAction("❌ Delete Task (and children)", self)

        if selected_item:
            # 只有选中了节点，才能添加子节点或删除
            add_child_action.triggered.connect(lambda: self.main_window._add_node(as_child=True))
            context_menu.addAction(add_child_action)

            # 根节点不能添加同级或被删除
            if selected_item.parent():
                add_sibling_action.triggered.connect(lambda: self.main_window._add_node(as_child=False))
                context_menu.addAction(add_sibling_action)
                context_menu.addSeparator()
                delete_action.triggered.connect(self.main_window._delete_selected_node)
                context_menu.addAction(delete_action)
        else:
            # 如果在空白处右键，则添加顶级项目
            add_toplevel_action = QAction("➕ Add Top-Level Project", self)
            add_toplevel_action.triggered.connect(lambda: self.main_window._add_node(as_toplevel=True))
            context_menu.addAction(add_toplevel_action)

        context_menu.exec(event.globalPos())
        
    def dropEvent(self, event):
        """处理拖放事件，更新数据结构。"""
        super().dropEvent(event)
        self.main_window._rebuild_data_from_tree()


class ResearchGUI(QMainWindow):
    """一个支持层级管理的科研项目GUI。"""

    def __init__(self):
        super().__init__()
        self.data = self._load_data()
        self.current_node_id = None
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("Hierarchical Research Project Manager")
        self.setGeometry(200, 200, 1200, 800)
        
        # ... (UI布局代码与之前版本基本相同，除了TreeWidget的实例化)
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        self.main_layout = QHBoxLayout(main_widget)

        self.tree_widget = ResearchTreeWidget(self)
        self.tree_widget.setHeaderLabels(["Project Structure"]) # 设置表头
        self.tree_widget.itemSelectionChanged.connect(self._on_node_selected)
        self.main_layout.addWidget(self.tree_widget, 4) # 权重调整

        details_scroll_area = QScrollArea()
        details_scroll_area.setWidgetResizable(True)
        details_container = QWidget()
        self.details_layout = QFormLayout(details_container)
        self.details_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        
        self.id_input = QLineEdit()
        self.id_input.setReadOnly(True)
        self.name_input = QLineEdit()
        self.status_input = QLineEdit()
        self.description_area = QTextEdit()
        self.notes_area = QTextEdit()
        
        # 移除 dependencies 和 unlocks，因为层级关系已隐含依赖
        self.details_layout.addRow(QLabel("ID (Read-Only):"), self.id_input)
        self.details_layout.addRow(QLabel("Name:"), self.name_input)
        self.details_layout.addRow(QLabel("Status:"), self.status_input)
        self.details_layout.addRow(QLabel("Description:"), self.description_area)
        self.details_layout.addRow(QLabel("Notes:"), self.notes_area)

        details_scroll_area.setWidget(details_container)
        self.main_layout.addWidget(details_scroll_area, 6)

        self._create_actions()
        self._create_menu_and_toolbar()
        self.setStatusBar(QStatusBar(self))

        self._refresh_tree()
        self._clear_details_pane()

    def _create_actions(self):
        self.save_action = QAction("💾 &Save Changes", self)
        self.save_action.setShortcut("Ctrl+S")
        self.save_action.triggered.connect(self._update_current_node)
        
        self.quit_action = QAction("🚪 &Quit", self)
        self.quit_action.setShortcut("Ctrl+Q")
        self.quit_action.triggered.connect(self.close)

    def _create_menu_and_toolbar(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&File")
        file_menu.addAction(self.save_action)
        file_menu.addSeparator()
        file_menu.addAction(self.quit_action)

        toolbar = QToolBar("Main Toolbar")
        self.addToolBar(toolbar)
        toolbar.addAction(self.save_action)

    def _load_data(self):
        if not DATA_FILE.exists():
            # 创建一个默认的空项目结构
            return [{'id': 'root', 'name': 'My Research Portfolio', 'children': []}]
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or []
        except Exception as e:
            QMessageBox.critical(self, "Load Error", f"Failed to load YAML file: {e}")
            return []

    def _commit_data_to_file(self):
        """将整个 self.data 写入文件。"""
        try:
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                yaml.dump(self.data, f, allow_unicode=True, sort_keys=False, indent=2)
            self.statusBar().showMessage("💾 Project saved successfully!", 3000)
            return True
        except Exception as e:
            self.statusBar().showMessage(f"Error saving file: {e}", 5000)
            return False

    # --- 递归辅助函数 ---
    def _find_node_by_id_recursive(self, node_id, nodes_list):
        """递归地在节点列表中查找具有给定ID的节点及其父列表。"""
        for i, node in enumerate(nodes_list):
            if node.get('id') == node_id:
                return node, nodes_list, i
            children = node.get('children')
            if children:
                found_node, parent_list, index = self._find_node_by_id_recursive(node_id, children)
                if found_node:
                    return found_node, parent_list, index
        return None, None, -1

    def _populate_tree_recursive(self, parent_item, nodes_list):
        """递归地用数据填充QTreeWidget。"""
        status_icons = {"Completed": "✅", "In-Progress": "⏳", "Unlocked": "🔓", "Locked": "🔒", "Blocked": "❌", "Planning": "🗓️"}
        for node_data in nodes_list:
            icon = status_icons.get(node_data.get('status'), "🔹")
            tree_item = QTreeWidgetItem(parent_item)
            tree_item.setText(0, f"{icon} {node_data.get('name', 'Unnamed')}")
            tree_item.setData(0, Qt.ItemDataRole.UserRole, node_data.get('id'))
            if node_data.get('children'):
                self._populate_tree_recursive(tree_item, node_data.get('children'))

    # --- CRUD + 树状结构管理 ---
    
    def _add_node(self, as_child=False, as_toplevel=False):
        """核心的添加节点函数。"""
        selected_item = self.tree_widget.currentItem()
        
        if not selected_item and not as_toplevel:
            QMessageBox.warning(self, "Selection Error", "Please select a node first.")
            return

        new_id = f"item_{uuid.uuid4().hex[:8]}"
        new_node = {
            'id': new_id,
            'name': "New Item - Edit Me",
            'status': "Locked",
            'description': "",
            'notes': "",
            'children': []
        }

        if as_toplevel:
            self.data.append(new_node)
        else:
            parent_id = selected_item.data(0, Qt.ItemDataRole.UserRole)
            parent_node, parent_list, parent_index = self._find_node_by_id_recursive(parent_id, self.data)
            
            if not parent_node: return

            if as_child:
                if 'children' not in parent_node:
                    parent_node['children'] = []
                parent_node['children'].append(new_node)
            else: # as sibling
                parent_list.insert(parent_index + 1, new_node)
        
        self._refresh_tree()
        self._rebuild_data_from_tree() # 立即保存新结构
        # 自动选中新节点
        self.select_node_in_tree(new_id)


    def _delete_selected_node(self):
        """删除选中的节点及其所有子节点。"""
        if not self.current_node_id: return
        
        node_to_delete, parent_list, index = self._find_node_by_id_recursive(self.current_node_id, self.data)
        if not node_to_delete: return

        reply = QMessageBox.question(
            self, "Confirm Deletion",
            f"Are you sure you want to permanently delete '{node_to_delete['name']}' and ALL its children?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            del parent_list[index]
            self.current_node_id = None
            self._clear_details_pane()
            self._refresh_tree()
            self._rebuild_data_from_tree() # 立即保存

    def _update_current_node(self):
        """更新当前节点的数据。"""
        if not self.current_node_id: return
        
        node, _, _ = self._find_node_by_id_recursive(self.current_node_id, self.data)
        if not node: return
        
        # 更新数据
        node['name'] = self.name_input.text()
        node['status'] = self.status_input.text()
        node['description'] = self.description_area.toPlainText()
        node['notes'] = self.notes_area.toPlainText()

        # 立即保存并刷新UI
        if self._commit_data_to_file():
            self._refresh_tree()


    def _rebuild_data_from_tree(self):
        """从QTreeWidget的当前状态重建self.data（在拖放后调用）。"""
        def build_list_recursive(parent_item):
            child_list = []
            for i in range(parent_item.childCount()):
                child_item = parent_item.child(i)
                node_id = child_item.data(0, Qt.ItemDataRole.UserRole)
                # 从旧数据中找到节点以保留所有信息
                node_data, _, _ = self._find_node_by_id_recursive(node_id, self.data)
                if node_data:
                    # 递归构建子节点
                    node_data['children'] = build_list_recursive(child_item)
                    child_list.append(node_data)
            return child_list

        self.data = build_list_recursive(self.tree_widget.invisibleRootItem())
        self._commit_data_to_file()
        self._refresh_tree() # 刷新以确保显示一致

    # --- UI更新方法 ---
    def _refresh_tree(self):
        """清空并用层级数据重新填充树。"""
        current_id = self.current_node_id
        self.tree_widget.clear()
        self._populate_tree_recursive(self.tree_widget.invisibleRootItem(), self.data)
        self.tree_widget.expandAll() # 默认展开所有节点
        if current_id:
            self.select_node_in_tree(current_id)

    def select_node_in_tree(self, node_id):
        """在树中找到并选中指定ID的节点。"""
        iterator = QTreeWidgetItemIterator(self.tree_widget)
        while iterator.value():
            item = iterator.value()
            if item.data(0, Qt.ItemDataRole.UserRole) == node_id:
                self.tree_widget.setCurrentItem(item)
                break
            iterator += 1
            
    def _on_node_selected(self):
        selected_item = self.tree_widget.currentItem()
        if not selected_item:
            self._clear_details_pane()
            self.current_node_id = None
            return

        node_id = selected_item.data(0, Qt.ItemDataRole.UserRole)
        self.current_node_id = node_id
        node_data, _, _ = self._find_node_by_id_recursive(node_id, self.data)
        
        if node_data:
            self.id_input.setText(node_data.get('id', ''))
            self.name_input.setText(node_data.get('name', ''))
            self.status_input.setText(node_data.get('status', ''))
            self.description_area.setPlainText(node_data.get('description', ''))
            self.notes_area.setPlainText(node_data.get('notes', ''))
        else:
            self._clear_details_pane()

    def _clear_details_pane(self):
        for i in range(self.details_layout.count()):
            widget = self.details_layout.itemAt(i).widget()
            if isinstance(widget, QLineEdit) or isinstance(widget, QTextEdit):
                widget.clear()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ResearchGUI()
    window.show()
    sys.exit(app.exec())
