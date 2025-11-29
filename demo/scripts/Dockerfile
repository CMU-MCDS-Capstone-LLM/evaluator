FROM python:3.11-slim

# Install git (needed for git operations in the container)
RUN apt-get update && \
    apt-get install -y git && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /workspace

# Install Python dependencies
# We install both pandas and polars since different branches use different libraries
RUN pip install --no-cache-dir \
    pandas>=1.3.0 \
    polars>=0.18.0 \
    pytest>=6.0

# Copy the foobar repository (with all git history and branches)
COPY data/repos/foobar /workspace/foobar

# Set git config (needed for git operations)
RUN git config --global user.email "demo@example.com" && \
    git config --global user.name "Demo User"

# Verify git repo structure
RUN cd /workspace/foobar && git branch -a && git status

# Keep container running
CMD ["tail", "-f", "/dev/null"]
