(() => {
  const tabs = document.querySelector("[data-creation-tabs]");
  if (tabs) {
    tabs.addEventListener("click", (event) => {
      const button = event.target.closest("[data-tab]");
      if (!button) return;
      tabs.querySelectorAll("button").forEach((item) => item.classList.toggle("is-active", item === button));
      document.querySelectorAll("[data-panel]").forEach((panel) => panel.classList.toggle("is-active", panel.dataset.panel === button.dataset.tab));
      if (button.dataset.tab === "ai") {
        const aiForm = document.querySelector("[data-ai-generate-form]");
        const aiLesson = aiForm && aiForm.querySelector("[name='lesson_id']");
        const manualLesson = document.querySelector("[data-map-form] [name='lesson_id']");
        if (aiForm && aiLesson) {
          if (manualLesson && manualLesson.value) aiLesson.value = manualLesson.value;
          if (aiLesson.value) aiForm.requestSubmit();
        }
      }
    });
  }

  const form = document.querySelector("[data-map-form]");
  if (!form) return;

  const labelInput = form.querySelector("[data-node-label]");
  const parentSelect = form.querySelector("[data-parent-node]");
  const canvas = form.querySelector("[data-builder-canvas]");
  const hiddenInput = form.querySelector("[name='nodes_json']");
  const countLabel = form.querySelector("[data-tree-count]");
  let nodes = [];
  let edges = [];
  let draggedKey = null;
  let sequence = 0;

  const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[char]));

  const rootNode = () => nodes[0] || null;
  const childrenOf = (key) => edges.filter((edge) => edge.source === key)
    .map((edge) => nodes.find((node) => node.key === edge.target))
    .filter(Boolean);

  const parentOf = (key) => edges.find((edge) => edge.target === key)?.source || "";

  const isInSubtree = (candidateKey, ancestorKey) => {
    if (candidateKey === ancestorKey) return true;
    return childrenOf(ancestorKey).some((child) => isInSubtree(candidateKey, child.key));
  };

  const setParent = (childKey, parentKey) => {
    const root = rootNode();
    if (!root || childKey === root.key || childKey === parentKey) return;
    if (parentKey && isInSubtree(parentKey, childKey)) return;
    edges = edges.filter((edge) => edge.target !== childKey);
    if (parentKey) edges.push({ source: parentKey, target: childKey, label: "يتفرع إلى" });
    sync();
  };

  const refreshParentChoices = () => {
    const previous = parentSelect.value;
    const root = rootNode();
    parentSelect.innerHTML = '<option value="">الفكرة الرئيسية / بدون أصل</option>' +
      nodes.map((node) => '<option value="' + escapeHtml(node.key) + '">' + escapeHtml(node.label) + '</option>').join("");
    if (previous && nodes.some((node) => node.key === previous)) {
      parentSelect.value = previous;
    } else if (root && nodes.length > 1) {
      parentSelect.value = root.key;
    } else {
      parentSelect.value = "";
    }
  };

  const assignPositions = () => {
    let leafIndex = 0;
    const visit = (node, depth) => {
      const children = childrenOf(node.key);
      node.x = depth * 300;
      if (!children.length) {
        node.y = leafIndex * 155;
        leafIndex += 1;
        return node.y;
      }
      const positions = children.map((child) => visit(child, depth + 1));
      node.y = (positions[0] + positions[positions.length - 1]) / 2;
      return node.y;
    };
    if (rootNode()) visit(rootNode(), 0);
    // Any disconnected node is kept visible as a separate root instead of being silently lost.
    nodes.forEach((node, index) => {
      if (node.x === undefined || node.y === undefined) {
        node.x = 0;
        node.y = (leafIndex + index) * 155;
      }
    });
  };

  const renderNode = (node, depth) => {
    const children = childrenOf(node.key);
    const parent = parentOf(node.key);
    const tone = node.tone || "gold";
    const isRoot = node.key === rootNode()?.key;
    const item = document.createElement("li");
    item.className = "tree-branch" + (isRoot ? " is-root-branch" : "");
    const card = document.createElement("article");
    card.className = "builder-node tree-node-card tone-" + tone + (isRoot ? " root-node" : "");
    card.draggable = !isRoot;
    card.dataset.nodeKey = node.key;
    card.innerHTML =
      '<div class="tree-node-card-top"><span class="tree-node-kind">' + (isRoot ? "الفكرة الرئيسية" : "فرع") + '</span>' +
      '<div class="node-tools"><button type="button" data-tone aria-label="تغيير لون العقدة" title="تغيير اللون">◈</button>' +
      '<button type="button" data-delete aria-label="حذف العقدة وفروعها" title="حذف العقدة وفروعها">×</button></div></div>' +
      '<strong contenteditable="true" role="textbox" aria-label="عنوان المفهوم"></strong>' +
      '<small class="tree-node-parent">' + (parent ? "يتفرع من: " + escapeHtml(nodes.find((item) => item.key === parent)?.label || "") : "جذر الشجرة") + '</small>' +
      '<span class="tree-drop-hint">أفلتي هنا لنقل الفرع</span>';
    const title = card.querySelector("strong");
    title.textContent = node.label;
    title.addEventListener("keydown", (event) => {
      if (event.key === "Enter") { event.preventDefault(); title.blur(); }
    });
    title.addEventListener("blur", () => {
      const value = title.textContent.trim();
      if (value) node.label = value.slice(0, 250);
      else title.textContent = node.label;
      sync();
    });
    card.querySelector("[data-tone]").addEventListener("click", () => {
      const tones = ["gold", "blue", "rose", "navy"];
      node.tone = tones[(tones.indexOf(tone) + 1) % tones.length];
      sync();
    });
    card.querySelector("[data-delete]").addEventListener("click", () => {
      const removing = new Set();
      const collect = (key) => {
        removing.add(key);
        childrenOf(key).forEach((child) => collect(child.key));
      };
      collect(node.key);
      nodes = nodes.filter((item) => !removing.has(item.key));
      edges = edges.filter((edge) => !removing.has(edge.source) && !removing.has(edge.target));
      sync();
    });
    card.addEventListener("dragstart", (event) => {
      draggedKey = node.key;
      event.dataTransfer?.setData("text/plain", node.key);
      if (event.dataTransfer) event.dataTransfer.effectAllowed = "move";
      card.classList.add("is-dragging");
    });
    card.addEventListener("dragend", () => {
      draggedKey = null;
      card.classList.remove("is-dragging");
      canvas.querySelectorAll(".is-drop-target").forEach((item) => item.classList.remove("is-drop-target"));
    });
    card.addEventListener("dragover", (event) => {
      if (!draggedKey || draggedKey === node.key || isInSubtree(node.key, draggedKey) || draggedKey === rootNode()?.key) return;
      event.preventDefault();
      card.classList.add("is-drop-target");
      if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
    });
    card.addEventListener("dragleave", (event) => {
      if (!card.contains(event.relatedTarget)) card.classList.remove("is-drop-target");
    });
    card.addEventListener("drop", (event) => {
      event.preventDefault();
      event.stopPropagation();
      card.classList.remove("is-drop-target");
      const key = draggedKey || event.dataTransfer?.getData("text/plain");
      if (key) setParent(key, node.key);
    });
    item.appendChild(card);
    if (children.length) {
      const list = document.createElement("ul");
      list.className = "tree-children";
      children.forEach((child) => list.appendChild(renderNode(child, depth + 1)));
      item.appendChild(list);
    }
    return item;
  };

  const sync = () => {
    assignPositions();
    hiddenInput.value = JSON.stringify({ nodes, edges });
    countLabel.textContent = nodes.length + (nodes.length === 1 ? " مفهوم" : " مفاهيم");
    refreshParentChoices();
    canvas.innerHTML = "";
    if (!nodes.length) {
      canvas.innerHTML = '<div class="tree-empty-state"><span>✧</span><strong>ابدئي من الفكرة الرئيسية</strong><p>اكتبي عنوان الموضوع ثم اضغطي «إضافة إلى الشجرة» لبناء أول عقدة.</p></div>';
      return;
    }
    const root = rootNode();
    const tree = document.createElement("ul");
    tree.className = "concept-tree";
    tree.appendChild(renderNode(root, 0));
    canvas.appendChild(tree);
    canvas.ondrop = (event) => {
      if (event.target !== canvas) return;
      event.preventDefault();
      const key = draggedKey || event.dataTransfer?.getData("text/plain");
      if (key && key !== rootNode()?.key) setParent(key, rootNode()?.key || "");
    };
  };

  canvas.addEventListener("dragover", (event) => {
    if (event.target === canvas && draggedKey && draggedKey !== rootNode()?.key) event.preventDefault();
  });

  form.querySelector("[data-add-node]").addEventListener("click", () => {
    const value = labelInput.value.trim();
    if (!value) { labelInput.focus(); return; }
    if (nodes.length >= 80) { alert("وصلت الخريطة إلى الحد الأقصى وهو 80 مفهومًا."); return; }
    const key = "node-" + Date.now() + "-" + (++sequence);
    const node = { key, label: value.slice(0, 250), description: "", tone: "gold", x: 0, y: 0 };
    if (!rootNode()) {
      nodes.push(node);
    } else {
      nodes.push(node);
      const parentKey = parentSelect.value || rootNode().key;
      if (parentKey !== key) edges.push({ source: parentKey, target: key, label: "يتفرع إلى" });
    }
    labelInput.value = "";
    sync();
    labelInput.focus();
  });

  labelInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") { event.preventDefault(); form.querySelector("[data-add-node]").click(); }
  });

  form.addEventListener("submit", (event) => {
    if (nodes.length < 2) {
      event.preventDefault();
      alert("أضيفي الفكرة الرئيسية وفرعًا واحدًا على الأقل قبل حفظ الخريطة.");
    }
  });

  sync();
})();
