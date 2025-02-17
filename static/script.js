//static/script.js
document.addEventListener('DOMContentLoaded', function() {
    // Ruby animation (only if rubies were earned)
    const rubyAnimation = document.getElementById('ruby-animation');
    if (rubyAnimation) {
        const rubies = rubyAnimation.querySelectorAll('.ruby');
        rubies.forEach((ruby, index) => {
            ruby.style.animationDelay = `${index * 0.1}s`;
            const xPos = Math.random() * 80;
            const yPos = Math.random() * 80;
            ruby.style.left = `${xPos}%`;
            ruby.style.top = `${yPos}%`;
        });
    }

});