// Main JavaScript functionality
document.addEventListener("DOMContentLoaded", () => {
  // Initialize tooltips
  var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
  var tooltipList = tooltipTriggerList.map((tooltipTriggerEl) => new window.bootstrap.Tooltip(tooltipTriggerEl))

  // Initialize popovers
  var popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'))
  var popoverList = popoverTriggerList.map((popoverTriggerEl) => new window.bootstrap.Popover(popoverTriggerEl))

  // Smooth scrolling for anchor links
  document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
    anchor.addEventListener("click", function (e) {
      e.preventDefault()
      const target = document.querySelector(this.getAttribute("href"))
      if (target) {
        target.scrollIntoView({
          behavior: "smooth",
          block: "start",
        })
      }
    })
  })

  // Auto-hide alerts after 5 seconds
  setTimeout(() => {
    const alerts = document.querySelectorAll(".alert:not(.alert-permanent)")
    alerts.forEach((alert) => {
      const bsAlert = new window.bootstrap.Alert(alert)
      bsAlert.close()
    })
  }, 5000)

  // Form validation enhancement
  const forms = document.querySelectorAll(".needs-validation")
  forms.forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!form.checkValidity()) {
        event.preventDefault()
        event.stopPropagation()
      }
      form.classList.add("was-validated")
    })
  })

  // Loading states for buttons
  document.querySelectorAll("form").forEach((form) => {
    form.addEventListener("submit", function () {
      const submitBtn = this.querySelector('button[type="submit"]')
      if (submitBtn && !submitBtn.disabled) {
        const originalText = submitBtn.innerHTML
        submitBtn.innerHTML = '<span class="loading me-2"></span>Procesando...'
        submitBtn.disabled = true

        // Re-enable after 10 seconds as fallback
        setTimeout(() => {
          submitBtn.innerHTML = originalText
          submitBtn.disabled = false
        }, 10000)
      }
    })
  })
})

// Utility functions
function formatCurrency(amount) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(amount)
}

function formatDate(dateString) {
  return new Intl.DateTimeFormat("es-ES", {
    year: "numeric",
    month: "long",
    day: "numeric",
  }).format(new Date(dateString))
}

// Global error handler
window.addEventListener("error", (e) => {
  console.error("Global error:", e.error)
  window.showToast("Ha ocurrido un error inesperado", "error")
})

// Service worker registration (for future PWA features)
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register("/sw.js")
      .then((registration) => {
        console.log("SW registered: ", registration)
      })
      .catch((registrationError) => {
        console.log("SW registration failed: ", registrationError)
      })
  })
}

// Declare showToast function
window.showToast = (message, type) => {
  const toastElement = document.createElement("div")
  toastElement.classList.add("toast", "bg-" + type)
  toastElement.role = "alert"
  toastElement.ariaLive = "assertive"
  toastElement.ariaAtomic = "true"
  toastElement.innerHTML =
    '<div class="toast-header"><strong class="me-auto">Notificación</strong><button type="button" class="btn-close" data-bs-dismiss="toast" aria-label="Close"></button></div><div class="toast-body">' +
    message +
    "</div>"
  document.body.appendChild(toastElement)
  new window.bootstrap.Toast(toastElement).show()
}
