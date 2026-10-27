// pymdownx.arithmatex (generic) 가 감싼 \( \) · \[ \] 만 MathJax 로 그린다
window.MathJax = {
  tex: { inline: [["\\(", "\\)"]], display: [["\\[", "\\]"]], processEscapes: true, processEnvironments: true },
  options: { ignoreHtmlClass: ".*|", processHtmlClass: "arithmatex" }
};
