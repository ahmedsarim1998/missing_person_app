/* =========================================================================
   locAIte front-end glue.
   - API helpers (fetch + JWT in localStorage)
   - Shared header/footer + auth-aware navigation injected into every page
   Loaded AFTER plugins.js (jQuery) but BEFORE designesia.js so the injected
   header markup exists when designesia.js binds the sticky menu / toggle.
   ========================================================================= */
(function () {
  "use strict";

  /* ---------------------------- API helpers ---------------------------- */
  var API = ""; // same origin (Flask serves this site)

  function token() { return localStorage.getItem("token"); }
  function role() { return localStorage.getItem("role"); }
  function username() { return localStorage.getItem("username"); }
  function isAuthed() { return !!token(); }
  function isAdmin() { return role() === "admin"; }

  function authHeaders() {
    var t = token();
    return t ? { Authorization: "Bearer " + t } : {};
  }

  async function handle(res) {
    var data = {};
    try { data = await res.json(); } catch (e) {}
    if (!res.ok) {
      throw new Error(data.msg || data.error || ("Request failed (" + res.status + ")"));
    }
    return data;
  }

  async function apiGet(path) {
    return handle(await fetch(API + path, { headers: authHeaders() }));
  }
  async function apiPost(path, body) {
    return handle(await fetch(API + path, {
      method: "POST",
      headers: Object.assign({ "Content-Type": "application/json" }, authHeaders()),
      body: JSON.stringify(body || {}),
    }));
  }
  async function apiPut(path, body) {
    return handle(await fetch(API + path, {
      method: "PUT",
      headers: Object.assign({ "Content-Type": "application/json" }, authHeaders()),
      body: JSON.stringify(body || {}),
    }));
  }
  async function apiPostForm(path, formData) {
    // NOTE: do not set Content-Type; the browser sets the multipart boundary.
    return handle(await fetch(API + path, {
      method: "POST",
      headers: authHeaders(),
      body: formData,
    }));
  }

  function login(data) {
    localStorage.setItem("token", data.access_token);
    localStorage.setItem("role", data.role);
    localStorage.setItem("username", data.username);
  }
  function logout() {
    localStorage.removeItem("token");
    localStorage.removeItem("role");
    localStorage.removeItem("username");
    window.location.href = "index.html";
  }

  /* Redirect to login if the page requires a role the user does not have. */
  function requireRole(roles) {
    if (!isAuthed()) {
      window.location.href = "login.html?next=" + encodeURIComponent(location.pathname + location.search);
      return false;
    }
    if (roles && roles.length && roles.indexOf(role()) === -1) {
      document.body.innerHTML =
        '<div style="padding:120px 20px;text-align:center;font-family:sans-serif">' +
        "<h2>Access denied</h2><p>This area is for administrators only.</p>" +
        '<a href="index.html">Back to home</a></div>';
      return false;
    }
    return true;
  }

  /* ------------------------- Header / footer --------------------------- */
  function headerHTML() {
    return [
      '<header class="transparent scroll-light">',
      '  <div id="topbar">',
      '    <div class="container"><div class="row"><div class="col-lg-12">',
      '      <div class="d-flex justify-content-between xs-hide">',
      '        <div class="d-flex">',
      '          <div class="topbar-widget me-3"><a href="#"><i class="icofont-location-pin"></i>IQRA University, Karachi, Pakistan</a></div>',
      '          <div class="topbar-widget me-3"><a href="#"><i class="icofont-phone"></i>+92 300 1234567</a></div>',
      '          <div class="topbar-widget me-3"><a href="#"><i class="icofont-envelope"></i>contact@locaite.com</a></div>',
      '        </div>',
      '        <div class="d-flex"><div class="social-icons">',
      '          <a href="#"><i class="fa-brands fa-facebook fa-lg"></i></a>',
      '          <a href="#"><i class="fa-brands fa-x-twitter fa-lg"></i></a>',
      '          <a href="#"><i class="fa-brands fa-instagram fa-lg"></i></a>',
      '        </div></div>',
      '      </div>',
      '    </div></div></div>',
      '  </div>',
      '  <div class="container"><div class="row"><div class="col-md-12">',
      '    <div class="de-flex sm-pt10">',
      '      <div class="de-flex-col">',
      '        <div id="logo"><a href="index.html">',
      '          <img class="logo-main" src="images/locaite-logo.png" alt="locAIte">',
      '          <img class="logo-mobile" src="images/locaite-logo.png" alt="locAIte">',
      '        </a></div>',
      '      </div>',
      '      <div class="de-flex-col header-col-mid">',
      '        <ul id="mainmenu"></ul>',
      '      </div>',
      '      <div class="de-flex-col">',
      '        <div class="menu_side_area" id="menu_side_area"></div>',
      '      </div>',
      '    </div>',
      '  </div></div></div>',
      "</header>",
    ].join("\n");
  }

  /* Canonical nav, shared by every page. Admin items only render for admins. */
  function menuHTML() {
    var adminBlock = isAdmin()
      ? '<li><a class="menu-item" href="#">Admin</a><ul>' +
        '<li><a href="dashboard.html">Dashboard</a></li>' +
        '<li><a href="sightings.html">Facebook Sightings</a></li>' +
        "</ul></li>"
      : "";
    return [
      '<li><a class="menu-item" href="index.html">Home</a></li>',
      '<li><a class="menu-item" href="cases.html">Cases</a></li>',
      '<li><a class="menu-item" href="report.html">Report Missing</a></li>',
      '<li><a class="menu-item" href="stream.html">Live Stream</a></li>',
      '<li><a class="menu-item" href="about.html">About</a><ul>' +
        '<li><a href="about.html">About</a></li>' +
        '<li><a href="services.html">Services</a></li>' +
        '<li><a href="team.html">Our Team</a></li>' +
        '<li><a href="gallery-filter.html">Gallery</a></li>' +
        "</ul></li>",
      '<li><a class="menu-item" href="contact.html">Contact</a></li>',
      adminBlock,
    ].join("\n");
  }

  function sideAreaHTML() {
    if (isAuthed()) {
      return (
        '<span class="me-3 text-white d-none d-lg-inline">Hi, ' + (username() || "user") + "</span>" +
        '<a href="#" id="logout-btn" class="btn-main fx-slide"><span>Logout</span></a>' +
        '<span id="menu-btn"></span>'
      );
    }
    return (
      '<a href="login.html" class="btn-main fx-slide btn-line me-2"><span>Login</span></a>' +
      '<a href="register.html" class="btn-main fx-slide"><span>Register</span></a>' +
      '<span id="menu-btn"></span>'
    );
  }

  function footerHTML() {
    return [
      '<footer class="text-light">',
      '  <div class="container"><div class="row g-4">',
      '    <div class="col-lg-4"><div class="widget">',
      '      <img src="images/locaite-logo.png" class="mb-3" alt="locAIte" style="height:40px">',
      '      <p>locAIte — AI Missing Person Recovery. Reuniting families using facial recognition and community reporting.</p>',
      "    </div></div>",
      '    <div class="col-lg-4"><div class="row"><div class="col-lg-6"><div class="widget">',
      "      <h5>Platform</h5><ul>",
      '        <li><a href="cases.html">Browse Cases</a></li>',
      '        <li><a href="report.html">Report Missing</a></li>',
      '        <li><a href="stream.html">Live Stream</a></li>',
      '        <li><a href="about.html">About Us</a></li>',
      "      </ul></div></div>",
      '      <div class="col-lg-6"><div class="widget"><h5>Company</h5><ul>',
      '        <li><a href="services.html">Services</a></li>',
      '        <li><a href="team.html">Our Team</a></li>',
      '        <li><a href="gallery-filter.html">Gallery</a></li>',
      '        <li><a href="contact.html">Contact</a></li>',
      "      </ul></div></div></div></div>",
      '    <div class="col-lg-4"><div class="widget"><h5>Contact Us</h5>',
      '      <div class="fw-bold text-white"><i class="icofont-location-pin me-2 id-color"></i>Head Office</div>IQRA University, Karachi, Pakistan',
      '      <div class="spacer-20"></div>',
      '      <div class="fw-bold text-white"><i class="icofont-envelope me-2 id-color"></i>Email Us</div>contact@locaite.com',
      "    </div></div>",
      "  </div></div>",
      '  <div class="subfooter"><div class="container"><div class="row"><div class="col-md-12">',
      '    <div class="de-flex"><div class="de-flex-col">&copy; 2025 - locAIte</div>',
      '    <ul class="menu-simple"><li><a href="#">Terms &amp; Conditions</a></li><li><a href="#">Privacy Policy</a></li></ul>',
      "    </div>",
      "  </div></div></div></div>",
      "</footer>",
    ].join("\n");
  }

  /* ------------------------- Wire it together -------------------------- */
  function buildChrome() {
    var headerHost = document.getElementById("site-header");
    if (headerHost && !headerHost.children.length) headerHost.innerHTML = headerHTML();

    var footerHost = document.getElementById("site-footer");
    if (footerHost && !footerHost.children.length) footerHost.innerHTML = footerHTML();

    // Replace menu + side buttons (works on marketing pages too).
    var menu = document.getElementById("mainmenu");
    if (menu) menu.innerHTML = menuHTML();

    var side = document.getElementById("menu_side_area") || document.querySelector(".menu_side_area");
    if (side) side.innerHTML = sideAreaHTML();

    var logoutBtn = document.getElementById("logout-btn");
    if (logoutBtn) {
      logoutBtn.addEventListener("click", function (e) {
        e.preventDefault();
        logout();
      });
    }
  }

  // Expose for page scripts.
  window.LOCAITE = {
    apiGet: apiGet, apiPost: apiPost, apiPut: apiPut, apiPostForm: apiPostForm,
    login: login, logout: logout, requireRole: requireRole,
    isAuthed: isAuthed, isAdmin: isAdmin, role: role, username: username,
    token: token,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", buildChrome);
  } else {
    buildChrome();
  }
})();
