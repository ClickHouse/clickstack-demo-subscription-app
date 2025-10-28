FROM golang:1.25-bookworm AS builder

WORKDIR /app

COPY ./go.mod go.mod
COPY ./go.sum go.sum

RUN go mod download

COPY ./main.go main.go

RUN CGO_ENABLED=0 GOOS=linux go build -ldflags "-s -w" -o myapp main.go

FROM alpine:latest

WORKDIR /root

COPY --from=builder /app/myapp ./

EXPOSE 9000
CMD ["./myapp"]
