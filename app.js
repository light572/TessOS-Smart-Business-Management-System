function toggleSidebar(){document.getElementById('sidebar').classList.toggle('open');document.getElementById('overlay').classList.toggle('show')}
function addSaleLine(){const box=document.getElementById('sale-items');const first=box.querySelector('.sale-line');const copy=first.cloneNode(true);copy.querySelector('input').value=1;box.appendChild(copy)}
