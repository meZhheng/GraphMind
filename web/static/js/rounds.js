(function () {
  const nav = document.querySelector("#roundsNav");
  const scrollEl = document.querySelector("#chatScroll");
  const roundButtons = new Map();
  let scrollFrame = 0;

  function setActive(turnId) {
    for (const [id, button] of roundButtons) {
      button.classList.toggle("active", id === turnId);
    }
  }

  function getScrollReferenceLine() {
    const rect = scrollEl
      ? scrollEl.getBoundingClientRect()
      : { top: 0, height: window.innerHeight };
    return rect.top + Math.min(160, rect.height * 0.28);
  }

  function updateActiveFromScroll() {
    scrollFrame = 0;
    if (!roundButtons.size) {
      return;
    }

    const firstTurnId = roundButtons.keys().next().value;
    const scrollTop = scrollEl ? scrollEl.scrollTop : window.scrollY;
    if (scrollTop <= 8 && firstTurnId) {
      setActive(firstTurnId);
      return;
    }

    const referenceLine = getScrollReferenceLine();
    let activeId = "";
    let activeDistance = Number.POSITIVE_INFINITY;

    for (const turnId of roundButtons.keys()) {
      const turn = document.getElementById(turnId);
      if (!turn) {
        continue;
      }

      const rect = turn.getBoundingClientRect();
      const distance = Math.abs(rect.top - referenceLine);
      if (distance < activeDistance) {
        activeId = turnId;
        activeDistance = distance;
      }
    }

    if (activeId) {
      setActive(activeId);
    }
  }

  function requestScrollUpdate() {
    if (scrollFrame) {
      return;
    }
    scrollFrame = requestAnimationFrame(updateActiveFromScroll);
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
    requestScrollUpdate();
  }

  function reset() {
    if (nav) {
      nav.innerHTML = "";
    }
    roundButtons.clear();
  }

  if (scrollEl) {
    scrollEl.addEventListener("scroll", requestScrollUpdate, { passive: true });
  }
  window.addEventListener("resize", requestScrollUpdate);

  window.GraphMindRounds = {
    addTurn,
    reset,
    setActive,
  };
})();
