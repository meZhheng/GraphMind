(function () {
  const nav = document.querySelector("#roundsNav");
  const roundButtons = new Map();

  function setActive(turnId) {
    for (const [id, button] of roundButtons) {
      button.classList.toggle("active", id === turnId);
    }
  }

  function addTurn(turnId, index) {
    if (!nav || roundButtons.has(turnId)) {
      return;
    }

    const button = document.createElement("button");
    button.className = "rounds-nav-item";
    button.type = "button";
    button.textContent = String(index);
    button.addEventListener("click", () => {
      document.querySelector(`#${turnId}`)?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
      setActive(turnId);
    });

    nav.append(button);
    roundButtons.set(turnId, button);
    setActive(turnId);
  }

  function reset() {
    if (nav) {
      nav.innerHTML = "";
    }
    roundButtons.clear();
  }

  window.GraphMindRounds = {
    addTurn,
    reset,
    setActive,
  };
})();
