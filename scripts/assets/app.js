(function () {
  const root = document.documentElement.getAttribute("data-root") || "";
  if (new URLSearchParams(location.search).has("captura")) {
    document.getElementById("cookie")?.remove();
  }
  const $ = (s, el) => (el || document).querySelector(s);

  // City search
  const q = $("#q");
  const results = $("#search-results");
  let cities = null;
  async function loadCities() {
    if (cities) return cities;
    const res = await fetch(root + "dados/busca.json");
    cities = await res.json();
    return cities;
  }
  function fold(s) {
    return (s || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase();
  }
  function renderList(items) {
    if (!results) return;
    if (!items.length) {
      results.style.display = "none";
      results.innerHTML = "";
      return;
    }
    results.style.display = "block";
    results.innerHTML = items
      .slice(0, 12)
      .map((c) => {
        if (c.publicado) {
          return `<li><a href="${root}municipio/${c.slug}/"><strong>${c.nome} (${c.uf})</strong><div class="tag">Página publicada</div></a></li>`;
        }
        return `<li><a href="${root}fila.html?ibge=${c.ibge}"><strong>${c.nome} (${c.uf})</strong><div class="tag">Ainda não publicada — na fila do roteiro noturno</div></a></li>`;
      })
      .join("");
  }
  document.getElementById("city-form")?.addEventListener("submit", (ev) => ev.preventDefault());
  if (q) {
    let t;
    q.addEventListener("input", () => {
      clearTimeout(t);
      t = setTimeout(async () => {
        const term = fold(q.value.trim());
        if (term.length < 2) {
          renderList([]);
          return;
        }
        const data = await loadCities();
        const found = data.filter((c) => fold(c.nome).includes(term) || fold(c.uf).startsWith(term));
        found.sort((a, b) => Number(b.publicado) - Number(a.publicado) || (b.populacao || 0) - (a.populacao || 0));
        renderList(found);
      }, 80);
    });
  }

  // CEP -> municipality via BrasilAPI (client-side only; no coverage claim)
  const cepForm = $("#cep-form");
  const cepOut = $("#cep-out");
  if (cepForm) {
    cepForm.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const cep = ($("#cep") || {}).value.replace(/\D/g, "");
      if (cep.length !== 8) {
        cepOut.textContent = "Informe um CEP com 8 dígitos. Isso só serve para achar o município, não a cobertura da rua.";
        return;
      }
      cepOut.textContent = "Consultando o município deste CEP…";
      try {
        const res = await fetch("https://brasilapi.com.br/api/cep/v2/" + cep);
        if (!res.ok) throw new Error("CEP não encontrado");
        const data = await res.json();
        const city = data.city || data.cidade;
        const uf = data.state || data.uf;
        const list = await loadCities();
        const hit = list.find((c) => fold(c.nome) === fold(city) && fold(c.uf) === fold(uf));
        if (hit && hit.publicado) {
          cepOut.innerHTML = `CEP ${cep} está em <strong>${hit.nome} (${hit.uf})</strong>. Os dados oficiais da Anatel usados aqui são municipais, não por bairro. <a href="${root}municipio/${hit.slug}/">Abrir a página do município</a>.`;
        } else if (hit) {
          cepOut.innerHTML = `CEP ${cep} está em <strong>${hit.nome} (${hit.uf})</strong>. Ainda não publicamos esta cidade; ela está na fila do roteiro noturno. Não afirmamos cobertura deste CEP.`;
        } else {
          cepOut.textContent = `O município informado para o CEP ${cep} foi ${city || "—"}/${uf || "—"}. Não encontramos esse nome na base processada. Os dados da Anatel neste site são por município, nunca por rua.`;
        }
      } catch (err) {
        cepOut.textContent = "Não foi possível consultar o CEP agora (serviço externo BrasilAPI). Busque pelo nome da cidade. Isso não indica cobertura.";
      }
    });
  }

  // Cookie notice: this site itself does not set marketing cookies.
  const cookie = $("#cookie");
  if (cookie && !localStorage.getItem("fnm-cookie-ok")) {
    cookie.classList.add("show");
    cookie.querySelector("form")?.addEventListener("submit", (ev) => {
      ev.preventDefault();
      localStorage.setItem("fnm-cookie-ok", "1");
      cookie.classList.remove("show");
    });
  }
})();
