// SPDX-License-Identifier: MIT
// Pytanie i komunikat w oknie strony, wspólne dla panelu przygotowania i panelu stanowiska (wici/stanowisko).
// Zamiast confirm/alert przeglądarki: przyciski po polsku, a strona działa dalej, gdy okno czeka na odpowiedź
// (odświeżanie kolejki, alarm). Esc i „Anuluj” znaczą nie; fokus startuje na „Anuluj”.
"use strict";

// buttons: [[napis, rodzaj przycisku ("primary", "danger", "ghost" albo ""), wartość]]; Promise z wartością
// klikniętego przycisku, false po Esc.
function dialog(text, buttons) {
  return new Promise(function (resolve) {
    var box = document.createElement("dialog"), row = document.createElement("div"), body = document.createElement("p");
    var value = false;
    box.className = "dialog";
    row.className = "buttons";
    body.textContent = text;
    buttons.forEach(function (b) {
      var node = document.createElement("button");
      node.type = "button";
      node.className = "btn" + (b[1] ? " btn-" + b[1] : "");
      node.textContent = b[0];
      node.addEventListener("click", function () { value = b[2]; box.close(); });
      row.appendChild(node);
    });
    box.appendChild(body);
    box.appendChild(row);
    box.addEventListener("close", function () { box.remove(); resolve(value); });
    document.body.appendChild(box);
    box.showModal();
  });
}

// Pytanie tak/nie; yes to napis przycisku zgody (czynność, nie „OK”), kind "danger" dla nieodwracalnych.
function ask(text, yes, kind) { return dialog(text, [["Anuluj", "ghost", false], [yes || "Tak", kind || "primary", true]]); }

function tell(text) { return dialog(text, [["Zamknij", "primary", true]]); }
