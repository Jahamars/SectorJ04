# plugins/error_counter_plugin.py
import grpc
from concurrent import futures
import logs_pb2, logs_pb2_grpc

class ErrorCounter(logs_pb2_grpc.LogProcessorServicer):
    def Process(self, request, context):
        errors = [log for log in request.logs if "error" in log.message.lower()]
        return logs_pb2.ProcessResponse(
            result=f"Найдено ошибок: {len(errors)}"
        )

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    logs_pb2_grpc.add_LogProcessorServicer_to_server(ErrorCounter(), server)
    server.add_insecure_port('[::]:50051')
    server.start()
    server.wait_for_termination()

if __name__ == "__main__":
    serve()
